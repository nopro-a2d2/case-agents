"""Headless stdio loop — reads prompts from stdin, writes StreamEvents as NDJSON to stdout.

Protocol:
  stdin:  one JSON line per user turn  {"prompt": "..."}
  stdout: one JSON line per StreamEvent (NDJSON)
  stderr: Python tracebacks / logs (forwarded to terminal)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from .runner import stream_query
from .types import (
    Done,
    SubagentTextDelta,
    SubagentToolEnd,
    SubagentToolStart,
    TextDelta,
    TodosUpdated,
    ToolEnd,
    ToolStart,
    TurnStart,
)


def _serialize(ev: Any) -> dict:
    if isinstance(ev, TurnStart):
        return {"type": "turn_start", "turn": ev.turn}
    if isinstance(ev, TextDelta):
        return {"type": "token", "text": ev.text}
    if isinstance(ev, ToolStart):
        return {"type": "tool_start", "id": ev.id, "name": ev.name, "input": ev.input}
    if isinstance(ev, ToolEnd):
        return {"type": "tool_end", "id": ev.id, "output": ev.output, "is_error": ev.is_error}
    if isinstance(ev, SubagentTextDelta):
        return {"type": "subagent_token", "tool_id": ev.tool_id, "text": ev.text}
    if isinstance(ev, SubagentToolStart):
        return {
            "type": "subagent_tool_start",
            "tool_id": ev.tool_id,
            "sub_id": ev.sub_id,
            "name": ev.name,
            "input": ev.input,
        }
    if isinstance(ev, SubagentToolEnd):
        return {
            "type": "subagent_tool_end",
            "tool_id": ev.tool_id,
            "sub_id": ev.sub_id,
            "output": ev.output,
            "is_error": ev.is_error,
        }
    if isinstance(ev, TodosUpdated):
        return {"type": "todos_updated", "todos": list(ev.todos)}
    if isinstance(ev, Done):
        t = ev.terminal
        return {
            "type": "done",
            "reason": t.reason,
            "final_text": t.final_text,
            "error": t.error,
        }
    return {"type": "unknown"}


def _emit(ev: Any) -> None:
    try:
        print(json.dumps(_serialize(ev), ensure_ascii=False, default=str), flush=True)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"type": "error", "error": str(e)}), flush=True)


async def headless_loop(case: str, root: str) -> None:
    """Run the agent loop in headless mode, bridging stdin/stdout."""
    from ..agent import build_case_agent_components
    from ..workspace import LocalFS

    ws = LocalFS(case_id=case, root=root)
    components = build_case_agent_components(ws)
    history: list[BaseMessage] = []

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"type": "error", "error": f"invalid json: {e}"}), flush=True)
            continue

        prompt: str = payload.get("prompt", "")
        force_strategy: bool = bool(payload.get("force_strategy", False))
        if not prompt:
            continue

        history.append(HumanMessage(content=prompt))
        async for ev in stream_query(
            prompt,
            components,
            messages=history,
            force_strategy=force_strategy,
        ):
            _emit(ev)
            if isinstance(ev, Done) and ev.terminal.messages:
                history = list(ev.terminal.messages)


__all__ = ["headless_loop"]
