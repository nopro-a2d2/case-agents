"""Case-bound memory: MEMORY.md index + per-entry frontmatter files.

Layout (relative to the case workspace root)::

    MEMORY.md            # one-line index of every stored memory
    memory/{name}.md     # individual memory with YAML-ish frontmatter

Memory types (no ethics / reference — out of scope for the MVP):

* ``user``     — 변호사 프로필 (전문 분야, 서면 스타일, 인용 형식 선호 등)
* ``feedback`` — 변호사가 준 교정·합의 사항 (반복 요구하지 않도록 보존)
* ``project``  — 사건 상태 추적 (사건번호·재판부·진행 단계·다음 기일·미해결 쟁점)

Index caps mirror Claude Code's memdir: 200 lines / 25 KB. They protect the
prompt budget — when full, the model is forced to consolidate rather than
silently dropping entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..workspace import Workspace


MemoryType = Literal["user", "feedback", "project"]
_VALID_TYPES: frozenset[str] = frozenset(("user", "feedback", "project"))

MEMORY_INDEX = "MEMORY.md"
MEMORY_DIR = "memory"

MEMORY_INDEX_MAX_LINES = 200
MEMORY_INDEX_MAX_BYTES = 25_000

_INDEX_HEADER = "# 사건 메모리 인덱스"
_FRONTMATTER_RE = re.compile(
    r"\A---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)\Z",
    re.DOTALL,
)
_NAME_RE = re.compile(r"\A[A-Za-z0-9_\-가-힣]+\Z")


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MemoryEntry:
    name: str
    description: str
    type: MemoryType
    body: str

    def to_file_text(self) -> str:
        return (
            "---\n"
            f"name: {self.name}\n"
            f"description: {self.description}\n"
            f"type: {self.type}\n"
            "---\n\n"
            f"{self.body.rstrip()}\n"
        )

    @classmethod
    def from_file_text(cls, text: str) -> "MemoryEntry":
        m = _FRONTMATTER_RE.match(text)
        if not m:
            raise ValueError("memory file missing frontmatter (--- ... ---)")
        meta: dict[str, str] = {}
        for line in m.group("frontmatter").splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        mtype = meta.get("type", "")
        if mtype not in _VALID_TYPES:
            raise ValueError(f"invalid memory type: {mtype!r}")
        return cls(
            name=meta.get("name", ""),
            description=meta.get("description", ""),
            type=mtype,  # type: ignore[arg-type]
            body=m.group("body").strip(),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "body": self.body,
        }


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _validate_name(name: str) -> str:
    base = name[:-3] if name.endswith(".md") else name
    if not base or not _NAME_RE.match(base):
        raise ValueError(
            f"invalid memory name: {name!r} "
            f"(allowed: alphanumerics, hyphen, underscore, hangul; .md optional)"
        )
    return base


def _memory_path(name: str) -> str:
    base = _validate_name(name)
    return f"{MEMORY_DIR}/{base}.md"


def _index_line(entry: MemoryEntry) -> str:
    return (
        f"- [{entry.name}]({MEMORY_DIR}/{entry.name}.md) "
        f"— {entry.description} ({entry.type})"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_memory_index(workspace: Workspace) -> str:
    """Return raw MEMORY.md content; empty string if absent."""
    if workspace.exists(MEMORY_INDEX):
        return workspace.read(MEMORY_INDEX)
    return ""


def list_memories(workspace: Workspace) -> list[MemoryEntry]:
    """Read every memory file under memory/. Skips malformed files silently."""
    if not workspace.exists(MEMORY_DIR):
        return []
    out: list[MemoryEntry] = []
    for path in workspace.glob(f"{MEMORY_DIR}/*.md"):
        try:
            out.append(MemoryEntry.from_file_text(workspace.read(path)))
        except (ValueError, FileNotFoundError):
            continue
    out.sort(key=lambda e: (e.type, e.name))
    return out


def read_memory(workspace: Workspace, name: str) -> MemoryEntry:
    return MemoryEntry.from_file_text(workspace.read(_memory_path(name)))


def write_memory(workspace: Workspace, entry: MemoryEntry) -> str:
    """Write a memory file, then refresh MEMORY.md index. Returns the file path."""
    if entry.type not in _VALID_TYPES:
        raise ValueError(f"invalid memory type: {entry.type!r}")
    _validate_name(entry.name)
    path = _memory_path(entry.name)
    workspace.write(path, entry.to_file_text())
    _refresh_index(workspace, entry)
    return path


# ---------------------------------------------------------------------------
# Index maintenance
# ---------------------------------------------------------------------------


def _refresh_index(workspace: Workspace, entry: MemoryEntry) -> None:
    current = read_memory_index(workspace)
    new_line = _index_line(entry)

    if current.strip():
        lines = current.splitlines()
    else:
        lines = [_INDEX_HEADER, ""]

    if not lines or not lines[0].startswith("# "):
        lines = [_INDEX_HEADER, ""] + lines

    prefix = f"- [{entry.name}]("
    for i, ln in enumerate(lines):
        if ln.startswith(prefix):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)

    new_text = "\n".join(lines).rstrip() + "\n"
    encoded = new_text.encode("utf-8")
    if len(encoded) > MEMORY_INDEX_MAX_BYTES:
        raise ValueError(
            f"MEMORY.md exceeds {MEMORY_INDEX_MAX_BYTES} byte cap "
            f"({len(encoded)} bytes); consolidate or remove entries"
        )
    line_count = new_text.count("\n")
    if line_count > MEMORY_INDEX_MAX_LINES:
        raise ValueError(
            f"MEMORY.md exceeds {MEMORY_INDEX_MAX_LINES} line cap "
            f"({line_count} lines); consolidate or remove entries"
        )

    workspace.write(MEMORY_INDEX, new_text)
