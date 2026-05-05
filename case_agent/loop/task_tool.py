"""``task`` tool — the main agent's hook for delegating to a sub-agent.

Mirrors claude-code's ``AgentTool`` (tools/AgentTool/runAgent.ts:248-806):
the sub-agent runs the *same* :func:`query` loop with its own system
prompt, tool subset, and model — but only the final assistant text is
returned to the parent as a string. The sub-agent's transcript stays
out of the parent's context window.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool

from .query import DEFAULT_MAX_TURNS, initial_messages, query
from .types import Done, Terminal

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool


def build_task_tool(
    *,
    subagents: dict[str, dict[str, Any]],
    fallback_model: "BaseChatModel",
    max_turns: int = DEFAULT_MAX_TURNS,
) -> "BaseTool":
    """Create a ``task`` tool bound to the given sub-agent registry.

    The returned tool has signature ``task(subagent_name: str, prompt: str)``.
    On invocation it spins up an isolated :func:`query` over the named
    sub-agent's tools/model/prompt and returns the final assistant text.

    Args:
        subagents: ``{name: subagent_definition_dict}`` (deepagents shape).
            Each definition must carry ``system_prompt`` and ``tools``;
            ``model`` is optional (falls back to ``fallback_model``).
        fallback_model: model used when a sub-agent definition omits one.
        max_turns: per-sub-agent loop cap.
    """
    available = ", ".join(sorted(subagents)) or "(none registered)"

    async def _run(subagent_name: str, prompt: str) -> str:
        sa = subagents.get(subagent_name)
        if sa is None:
            return (
                f"unknown subagent: {subagent_name!r}. "
                f"available: {available}"
            )

        sub_tools: list[BaseTool] = list(sa.get("tools") or [])
        sub_system = sa.get("system_prompt") or ""
        sub_model = sa.get("model") or fallback_model

        final_text: str | None = None
        terminal: Terminal | None = None
        async for ev in query(
            messages=initial_messages(prompt),
            system_prompt=sub_system,
            tools=sub_tools,
            model=sub_model,
            max_turns=max_turns,
        ):
            if isinstance(ev, Done):
                terminal = ev.terminal
                final_text = ev.terminal.final_text
                break

        if terminal is None:
            return "subagent produced no terminal event"
        if terminal.reason == "completed":
            return final_text or ""
        if terminal.reason == "error":
            return f"subagent error: {terminal.error}"
        return f"subagent stopped: reason={terminal.reason}"

    def _sync(subagent_name: str, prompt: str) -> str:
        return asyncio.run(_run(subagent_name, prompt))

    descriptions = "\n".join(
        f"  - {name}: {sa.get('description', '(no description)')}"
        for name, sa in sorted(subagents.items())
    )

    return StructuredTool.from_function(
        coroutine=_run,
        func=_sync,
        name="task",
        description=(
            "Delegate a focused exploration or extraction job to an isolated "
            "sub-agent. The sub-agent runs in its own context window with its "
            "own tool subset; only its final summary text is returned to you.\n"
            "Available sub-agents:\n"
            f"{descriptions or '  (none)'}\n"
            "Args:\n"
            "  subagent_name: one of the names listed above.\n"
            "  prompt: instructions for the sub-agent (full natural language)."
        ),
    )


__all__ = ["build_task_tool"]
