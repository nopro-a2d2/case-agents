"""Translate our :mod:`case_agent.loop` events into TUI tuples.

The Textual layer expects four kinds of tuples:

* ``("token", text)``                    - append a chunk to the current turn
* ``("tool_start", id, name, inputs)``   - mount a fresh ToolCallBlock
* ``("tool_end",   id, output, error)``  - fill in & collapse the matching block
* ``("done",)``                          - assistant turn finished

We forward those by interpreting the loop's :class:`StreamEvent`s. The
``thread_id`` argument is accepted for API compatibility with the prior
LangGraph runner but is currently a no-op (no checkpointer wired yet —
see plan §위험과 미해결 항목).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..loop import (
    Done,
    TextDelta,
    ToolEnd,
    ToolStart,
    TurnStart,
    stream_query,
)

if TYPE_CHECKING:
    from ..agent import CaseAgentComponents


def _format_payload(payload: Any) -> str:
    """Pretty-print tool I/O for display. Falls back to ``repr`` on failure."""
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return repr(payload)


class AgentRunner:
    """Run our query loop and translate its event stream into TUI tuples."""

    def __init__(self, components: "CaseAgentComponents") -> None:
        self.components = components

    async def stream(
        self, prompt: str, *, thread_id: str | None = None
    ) -> AsyncIterator[tuple]:
        """Yield TUI events for one user turn.

        Args:
            prompt: latest user message.
            thread_id: accepted for compatibility, currently unused.
        """
        del thread_id  # reserved for future checkpointer integration
        async for ev in stream_query(prompt, self.components):
            if isinstance(ev, TextDelta):
                if ev.text:
                    yield ("token", ev.text)
            elif isinstance(ev, ToolStart):
                yield ("tool_start", ev.id, ev.name, _format_payload(ev.input))
            elif isinstance(ev, ToolEnd):
                payload = _format_payload(ev.output)
                err = payload if ev.is_error else None
                yield ("tool_end", ev.id, payload, err)
            elif isinstance(ev, Done):
                terminal = ev.terminal
                if terminal.reason != "completed":
                    note = (
                        f"\n\n_loop ended: {terminal.reason}"
                        + (f" — {terminal.error}" if terminal.error else "")
                        + "_"
                    )
                    yield ("token", note)
                yield ("done",)
                return
            elif isinstance(ev, TurnStart):
                # No TUI representation today; useful for future per-turn dividers.
                continue
        yield ("done",)
