"""Loop event and terminal types.

We deliberately do NOT redefine messages here — LangChain's
``BaseMessage`` (HumanMessage / AIMessage / ToolMessage / SystemMessage)
is the on-the-wire format. Anthropic content-block conversion is handled
by ``langchain-anthropic`` when the messages reach the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Union

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

TerminalReason = Literal["completed", "max_turns", "aborted", "error"]


@dataclass(frozen=True)
class Terminal:
    """Final outcome of a query() run."""

    reason: TerminalReason
    final_text: str | None = None
    error: str | None = None
    messages: tuple[BaseMessage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TurnStart:
    """Emitted at the top of each loop iteration (1-indexed)."""

    turn: int


@dataclass(frozen=True)
class TextDelta:
    """A streamed text chunk from the assistant."""

    text: str


@dataclass(frozen=True)
class ToolStart:
    """A tool call is about to be executed."""

    id: str
    name: str
    input: dict[str, Any]
    display: dict[str, str] | None = None  # {"action": "...", "subject": "..."} when known


@dataclass(frozen=True)
class ToolEnd:
    """A tool call finished (or errored)."""

    id: str
    output: Any
    is_error: bool


@dataclass(frozen=True)
class Done:
    """Final event — always the last item yielded."""

    terminal: Terminal


@dataclass(frozen=True)
class SubagentTextDelta:
    """A streamed text chunk from inside a subagent run."""

    tool_id: str  # parent task tool-call ID
    text: str


@dataclass(frozen=True)
class SubagentToolStart:
    """A tool call started inside a subagent run."""

    tool_id: str  # parent task tool-call ID
    sub_id: str
    name: str
    input: dict[str, Any]
    display: dict[str, str] | None = None


@dataclass(frozen=True)
class SubagentToolEnd:
    """A tool call finished inside a subagent run."""

    tool_id: str  # parent task tool-call ID
    sub_id: str
    output: Any
    is_error: bool


@dataclass(frozen=True)
class TodosUpdated:
    """The session todo list changed — emitted after a successful
    ``write_todos`` tool call. ``todos`` is a snapshot (list of dicts
    with ``content`` and ``status`` keys).
    """

    todos: tuple[dict[str, Any], ...]


StreamEvent = Union[
    TurnStart, TextDelta, ToolStart, ToolEnd,
    SubagentTextDelta, SubagentToolStart, SubagentToolEnd,
    TodosUpdated,
    Done,
]


def coerce_text(content: Any) -> str:
    """LangChain message content can be ``str`` or ``list[dict|str]``.

    Mirrors the helper in ``case_agent/tui/runner.py`` so both the loop
    and the TUI translation layer stay in sync.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, str):
                parts.append(blk)
            elif isinstance(blk, dict):
                t = blk.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return ""


__all__ = [
    "Done",
    "StreamEvent",
    "SubagentTextDelta",
    "SubagentToolEnd",
    "SubagentToolStart",
    "Terminal",
    "TerminalReason",
    "TextDelta",
    "TodosUpdated",
    "ToolEnd",
    "ToolStart",
    "TurnStart",
    "coerce_text",
]
