"""Session-scoped todo list tool, mirroring Claude Code's ``TodoWrite``.

The agent calls ``write_todos`` with the **entire** list every time; the
store overwrites prior contents. Lifetime is the lifetime of the
:class:`TodoStore` instance, which is created once per CLI run inside
:func:`case_agent.agent.build_case_agent_components`.

The loop in :mod:`case_agent.loop.query` reads the store after a
successful ``write_todos`` call and emits a ``TodosUpdated`` stream event
so the TUI can render the checklist reactively.
"""

from __future__ import annotations

import json
from typing import Literal, TypedDict

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator


TodoStatus = Literal["pending", "in_progress", "completed"]


class Todo(TypedDict):
    """One checklist entry — matches the LangChain DeepAgents shape."""

    content: str
    status: TodoStatus


class TodoStore:
    """Tiny mutable holder for the current todo list. Not thread-safe by
    design — the loop is single-threaded asyncio.
    """

    def __init__(self) -> None:
        self.todos: list[Todo] = []

    def replace(self, todos: list[Todo]) -> None:
        self.todos = list(todos)

    def snapshot(self) -> list[Todo]:
        return [dict(t) for t in self.todos]  # type: ignore[misc]


_VALID_STATUSES = {"pending", "in_progress", "completed"}


class _TodoItem(BaseModel):
    content: str = Field(..., min_length=1)
    status: TodoStatus

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_VALID_STATUSES)}, got {v!r}"
            )
        return v


def build_write_todos_tool(store: TodoStore):
    @tool
    def write_todos(todos: list[_TodoItem]) -> str:
        """Publish or update the agent's working checklist (replace-all).

        Pass the **entire** list every call — the store is overwritten.
        Statuses: ``pending`` (not started) · ``in_progress`` (active) ·
        ``completed`` (done).

        WHEN to use:
          - 작업이 ≥3 단계로 분해될 때 시작 시 한 번 호출.
          - 단계가 끝날 때마다 곧바로 ``completed`` 로 갱신하고 다음 단계를
            ``in_progress`` 로 표시.
          - ``in_progress`` 는 한 번에 **하나만** 유지.

        WHEN NOT to use:
          - 단일 사실 질의·한 줄 수정처럼 단계가 1개인 작업.
          - 동일한 리스트를 의미 없이 다시 쓰기.

        Returns JSON ``{"ok": true, "count": N}``.
        """
        normalized: list[Todo] = [
            {"content": t.content, "status": t.status} for t in todos
        ]
        store.replace(normalized)
        return json.dumps(
            {"ok": True, "count": len(normalized)}, ensure_ascii=False
        )

    return write_todos


__all__ = [
    "Todo",
    "TodoStatus",
    "TodoStore",
    "build_write_todos_tool",
]
