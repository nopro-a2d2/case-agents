"""Façade over :func:`query` for the CLI and TUI.

* :func:`run_query_oneshot` — collect the stream, return final text.
* :func:`stream_query` — re-yield :class:`StreamEvent`s for the TUI.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .query import DEFAULT_MAX_TURNS, initial_messages, query
from .types import Done, StreamEvent

if TYPE_CHECKING:
    from ..agent import CaseAgentComponents


async def stream_query(
    prompt: str,
    components: "CaseAgentComponents",
    *,
    max_turns: int = DEFAULT_MAX_TURNS,
    abort: asyncio.Event | None = None,
) -> AsyncIterator[StreamEvent]:
    """Yield raw :class:`StreamEvent`s as the loop runs."""
    async for ev in query(
        messages=initial_messages(prompt),
        system_prompt=components.system_prompt,
        tools=components.tools,
        model=components.model,
        max_turns=max_turns,
        abort=abort,
    ):
        yield ev


async def run_query_oneshot(
    prompt: str,
    components: "CaseAgentComponents",
    *,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> str:
    """Drive the loop to completion and return the final assistant text.

    Returns the empty string when the loop hits ``max_turns``, ``aborted``,
    or ``error`` without producing text — callers (CLI) should render that
    as "(empty reply)" rather than raising.
    """
    final_text: str | None = None
    async for ev in stream_query(prompt, components, max_turns=max_turns):
        if isinstance(ev, Done):
            final_text = ev.terminal.final_text
            return final_text or ""
    return final_text or ""


__all__ = ["run_query_oneshot", "stream_query"]
