"""LocalFS: data/{case_id}/... backend."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable

from case_agent.workspace.base import (
    READONLY_PREFIXES,
    Match,
    OutOfWorkspaceError,
    ReadOnlyError,
    Workspace,
    WorkspaceError,
)


class LocalFS(Workspace):
    """Local filesystem workspace bound to a case_id.

    Layout: {root}/{case_id}/<wiki-output|cache|json|sources|...>
    """

    def __init__(self, case_id: str, root: str | os.PathLike = "data"):
        if not case_id or "/" in case_id or ".." in case_id:
            raise ValueError(f"invalid case_id: {case_id!r}")
        self.case_id = case_id
        self.root = Path(root).resolve()
        self.case_root = (self.root / case_id).resolve()
        if not self.case_root.exists():
            raise WorkspaceError(f"case root does not exist: {self.case_root}")

    # ---- path helpers --------------------------------------------------

    def _resolve(self, path: str) -> Path:
        if path in ("", "."):
            return self.case_root
        if path.startswith("/"):
            raise OutOfWorkspaceError(f"absolute path not allowed: {path}")
        full = (self.case_root / path).resolve()
        try:
            full.relative_to(self.case_root)
        except ValueError as e:
            raise OutOfWorkspaceError(f"path escapes workspace: {path}") from e
        return full

    def _rel(self, p: Path) -> str:
        return str(p.relative_to(self.case_root))

    # ---- read-only protection ------------------------------------------

    def is_readonly(self, path: str) -> bool:
        head = path.split("/", 1)[0]
        return head in READONLY_PREFIXES

    def _ensure_writable(self, path: str) -> None:
        if self.is_readonly(path):
            raise ReadOnlyError(
                f"path is under read-only prefix: {path} "
                f"(read-only: {READONLY_PREFIXES})"
            )

    # ---- core ops ------------------------------------------------------

    def exists(self, path: str) -> bool:
        try:
            return self._resolve(path).exists()
        except OutOfWorkspaceError:
            return False

    def read(self, path: str, *, range: tuple[int, int] | None = None) -> str:
        full = self._resolve(path)
        if not full.is_file():
            raise FileNotFoundError(path)
        text = full.read_text(encoding="utf-8")
        if range is None:
            return text
        start, end = range  # 1-based, inclusive
        lines = text.splitlines()
        return "\n".join(lines[max(0, start - 1) : end])

    def write(self, path: str, content: str) -> None:
        self._ensure_writable(path)
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        self.audit(
            "write",
            path,
            {
                "bytes": len(content.encode("utf-8")),
                "sha1": hashlib.sha1(content.encode("utf-8")).hexdigest(),
            },
        )

    def edit(
        self,
        path: str,
        old: str,
        new: str,
        *,
        replace_all: bool = False,
    ) -> None:
        self._ensure_writable(path)
        full = self._resolve(path)
        if not full.is_file():
            raise FileNotFoundError(path)
        text = full.read_text(encoding="utf-8")
        if old not in text:
            raise WorkspaceError(f"old string not found in {path}")
        if not replace_all:
            count = text.count(old)
            if count > 1:
                raise WorkspaceError(
                    f"old string is not unique in {path} ({count} occurrences); "
                    f"pass replace_all=True or extend old string"
                )
            text2 = text.replace(old, new, 1)
            n = 1
        else:
            n = text.count(old)
            text2 = text.replace(old, new)
        full.write_text(text2, encoding="utf-8")
        self.audit("edit", path, {"replacements": n})

    def ls(self, path: str = ".") -> list[str]:
        full = self._resolve(path)
        if full.is_file():
            return [self._rel(full)]
        return sorted(self._rel(p) for p in full.iterdir())

    def glob(self, pattern: str) -> list[str]:
        # workspace-relative glob (recursive on **)
        results: list[str] = []
        # Use Path.glob from case_root; reject abs patterns.
        if pattern.startswith("/"):
            raise OutOfWorkspaceError(f"absolute glob not allowed: {pattern}")
        for p in self.case_root.glob(pattern):
            try:
                results.append(self._rel(p))
            except ValueError:
                continue
        return sorted(results)

    def grep(
        self,
        pattern: str,
        path: str = ".",
        *,
        regex: bool = True,
        max_results: int = 200,
    ) -> Iterable[Match]:
        rx = re.compile(pattern) if regex else None
        full = self._resolve(path)
        files: list[Path]
        if full.is_file():
            files = [full]
        else:
            files = [p for p in full.rglob("*") if p.is_file()]
        results: list[Match] = []
        for f in files:
            try:
                with f.open("r", encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh, 1):
                        line_no_nl = line.rstrip("\n")
                        hit = (
                            rx.search(line_no_nl)
                            if rx is not None
                            else (pattern in line_no_nl)
                        )
                        if hit:
                            results.append(
                                Match(
                                    path=self._rel(f),
                                    line=i,
                                    text=line_no_nl,
                                )
                            )
                            if len(results) >= max_results:
                                return results
            except (UnicodeDecodeError, OSError):
                continue
        return results

    # ---- audit ---------------------------------------------------------

    def audit(self, op: str, path: str, meta: dict) -> None:
        audit_dir = self.case_root / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(),
            "case_id": self.case_id,
            "op": op,
            "path": path,
            **meta,
        }
        log_path = audit_dir / "ops.jsonl"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
