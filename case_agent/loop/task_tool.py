"""``task`` tool — the main agent's hook for delegating to a sub-agent.

Mirrors claude-code's ``AgentTool`` (tools/AgentTool/runAgent.ts:248-806):
the sub-agent runs the *same* :func:`query` loop with its own system
prompt, tool subset, and model — but only the final assistant text is
returned to the parent as a string. The sub-agent's transcript stays
out of the parent's context window.

``StreamingTaskTool`` additionally exposes ``_arun_streaming()`` so that
:func:`query` can iterate subagent events and bubble them up to the TUI
as ``SubagentTextDelta`` / ``SubagentToolStart`` / ``SubagentToolEnd``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool
from pydantic import Field

from .query import DEFAULT_MAX_TURNS, initial_messages, query
from .types import Done, StreamEvent, Terminal

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool as BaseToolType


class StreamingTaskTool(BaseTool):
    """A ``task`` tool that exposes subagent events via ``_arun_streaming``.

    :func:`query` detects this class and iterates ``_arun_streaming`` instead
    of calling ``ainvoke``, allowing subagent ``TextDelta`` / ``ToolStart`` /
    ``ToolEnd`` events to be bubbled up to the TUI in real time.
    """

    name: str = "task"
    description: str = ""

    subagents: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fallback_model: Any = Field(default=None)
    max_turns: int = DEFAULT_MAX_TURNS

    # Required by BaseTool — sync fallback used only when ainvoke is unavailable.
    def _run(self, subagent_name: str, prompt: str) -> str:
        return asyncio.run(self._arun(subagent_name, prompt))

    async def _arun(
        self,
        subagent_name: str,
        prompt: str,
        _callbacks: list | None = None,
        _metadata: dict | None = None,
        _display_label_fn: Any = None,
    ) -> str:
        """Non-streaming path: run to completion and return final text."""
        final_text: str | None = None
        async for ev in self._arun_streaming(
            subagent_name,
            prompt,
            _callbacks=_callbacks,
            _metadata=_metadata,
            _display_label_fn=_display_label_fn,
        ):
            if isinstance(ev, Done):
                final_text = ev.terminal.final_text
                break
        return final_text or ""

    async def _arun_streaming(
        self,
        subagent_name: str,
        prompt: str,
        _callbacks: list | None = None,
        _metadata: dict | None = None,
        _display_label_fn: Any = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield all StreamEvents from the subagent loop.

        The last event is always a ``Done``. Callers (``query.py``) wrap
        ``TextDelta`` / ``ToolStart`` / ``ToolEnd`` into the corresponding
        ``Subagent*`` variants before re-yielding them upstream.
        """
        sa = self.subagents.get(subagent_name)
        if sa is None:
            available = ", ".join(sorted(self.subagents)) or "(none registered)"
            yield Done(
                Terminal(
                    "error",
                    error=(
                        f"unknown subagent: {subagent_name!r}. "
                        f"available: {available}"
                    ),
                )
            )
            return

        sub_tools: list[BaseToolType] = list(sa.get("tools") or [])
        sub_system: str = sa.get("system_prompt") or ""
        sub_model = sa.get("model") or self.fallback_model

        async for ev in query(
            messages=initial_messages(prompt),
            system_prompt=sub_system,
            tools=sub_tools,
            model=sub_model,
            max_turns=self.max_turns,
            callbacks=_callbacks,
            metadata=_metadata,
            display_label_fn=_display_label_fn,
        ):
            yield ev
            if isinstance(ev, Done):
                return


def build_task_tool(
    *,
    subagents: dict[str, dict[str, Any]],
    fallback_model: "BaseChatModel",
    max_turns: int = DEFAULT_MAX_TURNS,
) -> "BaseToolType":
    """Create a ``StreamingTaskTool`` bound to the given sub-agent registry."""
    descriptions = "\n".join(
        f"  - {name}: {sa.get('description', '(no description)')}"
        for name, sa in sorted(subagents.items())
    )
    available = ", ".join(sorted(subagents)) or "(none registered)"

    tool = StreamingTaskTool(
        subagents=subagents,
        fallback_model=fallback_model,
        max_turns=max_turns,
        description=(
            "Delegate a focused exploration or extraction job to an isolated "
            "sub-agent. The sub-agent runs in its own context window with its "
            "own tool subset; only its final summary text is returned to you.\n"
            "Available sub-agents:\n"
            f"{descriptions or '  (none)'}\n"
            "Args:\n"
            f"  subagent_name: one of {available}.\n"
            "  prompt: instructions for the sub-agent (full natural language)."
        ),
    )
    return tool


def build_task_tool_for_subagent(
    *,
    subagents: dict[str, dict[str, Any]],
    allowed: set[str],
    fallback_model: "BaseChatModel",
    max_turns: int = DEFAULT_MAX_TURNS,
) -> "BaseToolType":
    """Variant of :func:`build_task_tool` restricted to a whitelist of names.

    Used when injecting a ``task`` tool into another subagent so it can only
    delegate to the sub-sub-agents we explicitly allow (typically just
    ``"explore"``). This blocks infinite recursion and keeps the delegation
    graph flat: planning/writing subagents may call explore, but cannot call
    each other or themselves.
    """
    filtered = {k: v for k, v in subagents.items() if k in allowed}
    return build_task_tool(
        subagents=filtered, fallback_model=fallback_model, max_turns=max_turns
    )


__all__ = ["StreamingTaskTool", "build_task_tool", "build_task_tool_for_subagent"]
