"""Workspace abstraction: case_id-bound filesystem.

LocalFS maps to data/{case_id}/...; future S3FS to s3://{bucket}/case/{case_id}/...
Read-only protected directories: wiki-output/, cache/, json/, sources/, txt/.
Writable: artifacts/, drafts/, notes/, audit/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


READONLY_PREFIXES: tuple[str, ...] = (
    "wiki-output",
    "cache",
    "json",
    "sources",
    "txt",  # Some legacy cases store raw text under txt/ instead of sources/.
    "benchmark",
    "eval-output",
)

WRITABLE_PREFIXES: tuple[str, ...] = (
    "artifacts",
    "drafts",
    "notes",
    "audit",
)


class WorkspaceError(Exception):
    """Base error for workspace operations."""


class ReadOnlyError(WorkspaceError):
    """Attempted to write under a read-only prefix."""


class OutOfWorkspaceError(WorkspaceError):
    """Path attempted to escape the case workspace root."""


@dataclass(frozen=True, slots=True)
class Match:
    path: str        # workspace-relative path
    line: int        # 1-based line number
    text: str        # the matching line (no trailing newline)


class Workspace(Protocol):
    """Case-bound workspace contract.

    All `path` arguments are case-root-relative (e.g. "wiki-output/overview.md").
    Implementations must reject absolute paths and `..` escapes.
    """

    case_id: str

    def read(self, path: str, *, range: tuple[int, int] | None = None) -> str: ...

    def write(self, path: str, content: str) -> None: ...

    def edit(self, path: str, old: str, new: str, *, replace_all: bool = False) -> None: ...

    def ls(self, path: str = ".") -> list[str]: ...

    def glob(self, pattern: str) -> list[str]: ...

    def grep(
        self,
        pattern: str,
        path: str = ".",
        *,
        regex: bool = True,
        max_results: int = 200,
    ) -> Iterable[Match]: ...

    def is_readonly(self, path: str) -> bool: ...

    def exists(self, path: str) -> bool: ...

    def audit(self, op: str, path: str, meta: dict) -> None: ...
