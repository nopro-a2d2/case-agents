"""Session-scoped todo list tool, mirroring Claude Code's ``TodoWrite``.

The agent calls ``write_todos`` with the **entire** list every time; the
store overwrites prior contents. Lifetime is the lifetime of the
:class:`TodoStore` instance, which is created once per CLI run inside
:func:`case_agent.agent.build_case_agent_components`.

The loop in :mod:`case_agent.loop.query` snapshots the store before and
after every tool call; whenever it changes (``write_todos`` itself, or any
other tool that mutates the store such as Brief Mode's
``approve_brief_outline`` / ``write_brief_section``) it emits a
``TodosUpdated`` stream event so the TUI can render the checklist reactively.
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

        WHEN to use (의무):
          - 작업이 **≥2 단계** 로 분해되면 답변 전에 반드시 한 번 호출.
          - 각 단계 종료 시 즉시 다시 호출하여 status 갱신
            (끝난 것 → ``completed``, 다음 것 → ``in_progress``).
          - ``in_progress`` 는 한 번에 **하나만** 유지.
          - 검증 실패로 보강이 필요하면 새 todo 추가.
          - 모든 항목이 ``completed`` 가 된 뒤에 사용자에게 최종 답변.

        WHEN NOT to use (예외):
          - 한 줄 사실 질의("피고인이 누구야?", "공소제기일") 처럼
            ``smart_search`` 1회로 끝나는 1단계 작업.
          - 의미 없는 동일 리스트 재기록.

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
