"""Façade over :func:`query` for the CLI and TUI.

* :func:`run_query_oneshot` — collect the stream, return final text.
* :func:`stream_query` — re-yield :class:`StreamEvent`s for the TUI.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .brief_mode import BRIEF_FORCE_REMINDER
from .labels import build_label_fn
from .query import DEFAULT_MAX_TURNS, initial_messages, query
from .strategy_mode import STRATEGY_FORCE_REMINDER
from .types import Done, StreamEvent

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from ..agent import CaseAgentComponents


def _build_langfuse_metadata(
    session_id: str | None,
    user_id: str | None,
    tags: "list[str] | None",
) -> dict | None:
    """Build the LangChain ``metadata`` dict that Langfuse's CallbackHandler
    reads. Returns ``None`` when none of the fields are set so the loop
    keeps its zero-overhead path."""
    md: dict = {}
    if session_id:
        md["langfuse_session_id"] = session_id
    if user_id:
        md["langfuse_user_id"] = user_id
    if tags:
        md["langfuse_tags"] = list(tags)
    return md or None


async def stream_query(
    prompt: str,
    components: "CaseAgentComponents",
    *,
    messages: "list[BaseMessage] | None" = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    abort: asyncio.Event | None = None,
    stream_timeout: float | None = None,
    force_strategy: bool = False,
    force_brief: bool = False,
    callbacks: list | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: "list[str] | None" = None,
) -> AsyncIterator[StreamEvent]:
    """Yield raw :class:`StreamEvent`s as the loop runs.

    When ``force_strategy`` is True, the system prompt for *this turn* is
    composed with ``STRATEGY_FORCE_REMINDER`` so the model is pushed to call
    ``enter_strategy_mode`` as its first action. When ``force_brief`` is True,
    ``BRIEF_FORCE_REMINDER`` is used instead so the model is pushed toward
    ``enter_brief_mode``. Both flags are mutually exclusive (UI is enum); if
    both arrive True the brief flag wins. Toggling either flag off on a later
    turn restores the base system prompt — no history pollution.
    """
    system_prompt = components.system_prompt
    if force_brief:
        system_extra = BRIEF_FORCE_REMINDER
    elif force_strategy:
        system_extra = STRATEGY_FORCE_REMINDER
    else:
        system_extra = None

    input_messages = messages if messages is not None else initial_messages(prompt)

    # Auto-attach Langfuse callbacks unless caller passed an explicit list
    # (including an empty list to opt out).
    if callbacks is None:
        from ..observability import build_callbacks

        callbacks = build_callbacks()

    metadata = _build_langfuse_metadata(session_id, user_id, tags)
    display_label_fn = build_label_fn(components.workspace)

    async for ev in query(
        messages=input_messages,
        system_prompt=system_prompt,
        tools=components.tools,
        model=components.model,
        max_turns=max_turns,
        abort=abort,
        stream_timeout=stream_timeout,
        todos_store=getattr(components, "todos_store", None),
        callbacks=callbacks,
        metadata=metadata,
        system_extra=system_extra,
        display_label_fn=display_label_fn,
    ):
        yield ev


async def run_query_oneshot(
    prompt: str,
    components: "CaseAgentComponents",
    *,
    max_turns: int = DEFAULT_MAX_TURNS,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: "list[str] | None" = None,
) -> str:
    """Drive the loop to completion and return the final assistant text.

    Returns the empty string when the loop hits ``max_turns``, ``aborted``,
    or ``error`` without producing text — callers (CLI) should render that
    as "(empty reply)" rather than raising.
    """
    from ..observability import flush as _obs_flush

    final_text: str | None = None
    try:
        async for ev in stream_query(
            prompt,
            components,
            max_turns=max_turns,
            session_id=session_id,
            user_id=user_id,
            tags=tags,
        ):
            if isinstance(ev, Done):
                final_text = ev.terminal.final_text
                return final_text or ""
        return final_text or ""
    finally:
        _obs_flush()


__all__ = ["run_query_oneshot", "stream_query"]
