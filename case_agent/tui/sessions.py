"""Per-case named-session storage for the chat TUI.

A ``SessionStore`` owns:
  * a long-lived ``sqlite3.Connection`` wrapped in a LangGraph
    :class:`SqliteSaver` (the agent's checkpointer); and
  * a small ``index.json`` sidecar mapping human-readable session names
    (used as LangGraph ``thread_id``) to ``last_used`` and ``preview``
    fields for the in-TUI session picker.

Storage layout under ``data/{case}/sessions/``::

    checkpoints.sqlite   # LangGraph state per thread_id
    index.json           # {"sessions": {"<name>": {...}}}
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

DEFAULT_SESSION = "default"


@dataclass
class SessionMeta:
    name: str
    last_used: float
    preview: str

    def to_dict(self) -> dict:
        return {"last_used": self.last_used, "preview": self.preview}


class SessionStore:
    """Owns the sqlite connection + index.json sidecar for one case.

    The synchronous :class:`SqliteSaver` is created eagerly so callers can
    poke the schema (used by tests). The :class:`AsyncSqliteSaver` -
    which is what LangGraph's ``astream_events`` actually requires - must
    be created from inside a running event loop via :meth:`async_checkpointer`.
    """

    def __init__(self, case_root: Path) -> None:
        self.case_root = Path(case_root)
        self.sessions_dir = self.case_root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.sessions_dir / "checkpoints.sqlite"
        self.index_path = self.sessions_dir / "index.json"
        # check_same_thread=False: Textual workers may run on a different
        # thread than the one that opened the connection.
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self.checkpointer = SqliteSaver(self._conn)
        self._async_conn: aiosqlite.Connection | None = None
        self._async_checkpointer: AsyncSqliteSaver | None = None

    async def async_checkpointer(self) -> AsyncSqliteSaver:
        """Lazily open an aiosqlite connection and bind an AsyncSqliteSaver.

        Must be called from within a running event loop.
        """
        if self._async_checkpointer is None:
            self._async_conn = await aiosqlite.connect(str(self.db_path))
            self._async_checkpointer = AsyncSqliteSaver(self._async_conn)
            await self._async_checkpointer.setup()
        return self._async_checkpointer

    # ------------------------------------------------------------------ index

    def _read_index(self) -> dict[str, SessionMeta]:
        if not self.index_path.exists():
            return {}
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        out: dict[str, SessionMeta] = {}
        for name, meta in (raw.get("sessions") or {}).items():
            out[name] = SessionMeta(
                name=name,
                last_used=float(meta.get("last_used", 0.0)),
                preview=str(meta.get("preview", "")),
            )
        return out

    def _write_index(self, sessions: dict[str, SessionMeta]) -> None:
        payload = {"sessions": {n: m.to_dict() for n, m in sessions.items()}}
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ public

    def list_sessions(self) -> list[SessionMeta]:
        return sorted(
            self._read_index().values(), key=lambda m: m.last_used, reverse=True
        )

    def touch(self, name: str, *, preview: str | None = None) -> None:
        """Record activity on a session. Creates the entry if missing."""
        sessions = self._read_index()
        existing = sessions.get(name)
        sessions[name] = SessionMeta(
            name=name,
            last_used=time.time(),
            preview=preview if preview is not None else (existing.preview if existing else ""),
        )
        self._write_index(sessions)

    def delete(self, name: str) -> None:
        sessions = self._read_index()
        sessions.pop(name, None)
        self._write_index(sessions)
        # Also wipe LangGraph state for this thread so /clear is meaningful.
        # SqliteSaver stores rows keyed by thread_id; delete via raw SQL.
        with self._conn:
            self._conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (name,))
            self._conn.execute("DELETE FROM writes WHERE thread_id = ?", (name,))

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    async def aclose(self) -> None:
        """Close both the sync and async sqlite connections."""
        if self._async_conn is not None:
            try:
                await self._async_conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._async_conn = None
            self._async_checkpointer = None
        self.close()
