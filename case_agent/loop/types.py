"""Loop event and terminal types.

We deliberately do NOT redefine messages here — LangChain's
``BaseMessage`` (HumanMessage / AIMessage / ToolMessage / SystemMessage)
is the on-the-wire format. Anthropic content-block conversion is handled
by ``langchain-anthropic`` when the messages reach the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Union


TerminalReason = Literal["completed", "max_turns", "aborted", "error"]


@dataclass(frozen=True)
class Terminal:
    """Final outcome of a query() run."""

    reason: TerminalReason
    final_text: str | None = None
    error: str | None = None


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


StreamEvent = Union[TurnStart, TextDelta, ToolStart, ToolEnd, Done]


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
    "Terminal",
    "TerminalReason",
    "TextDelta",
    "ToolEnd",
    "ToolStart",
    "TurnStart",
    "coerce_text",
]
