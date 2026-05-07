"""Hand-rolled agentic loop modeled after claude-code's query.ts.

Owns the LLM↔Tool cycle so we control:
  - the explicit while-loop with stop_reason branching,
  - tool_result accumulation into the running message list,
  - abort handling, max_turns clamp, and stream events for the TUI.

Internally uses LangChain BaseMessage objects so the existing
ChatAnthropicVertex client and BaseTool wrappers plug in unchanged.
"""

from .runner import run_query_oneshot, stream_query
from .types import (
    Done,
    StreamEvent,
    SubagentTextDelta,
    SubagentToolEnd,
    SubagentToolStart,
    Terminal,
    TextDelta,
    TodosUpdated,
    ToolEnd,
    ToolStart,
    TurnStart,
)

__all__ = [
    "Done",
    "StreamEvent",
    "SubagentTextDelta",
    "SubagentToolEnd",
    "SubagentToolStart",
    "Terminal",
    "TextDelta",
    "TodosUpdated",
    "ToolEnd",
    "ToolStart",
    "TurnStart",
    "run_query_oneshot",
    "stream_query",
]
