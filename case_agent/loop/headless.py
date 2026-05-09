"""Headless stdio loop — reads prompts from stdin, writes StreamEvents as NDJSON to stdout.

Protocol:
  stdin:  one JSON line per frame
            {"prompt": "...", "force_strategy": false}   # start a turn
            {"type": "abort"}                            # cancel running turn
  stdout: one JSON line per StreamEvent (NDJSON)
  stderr: Python tracebacks / logs (forwarded to terminal)
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from ..commands import CommandContext, try_dispatch
from .runner import stream_query
from .slash import build_skills_list_event, expand_slash
from .types import (
    Cleared,
    Done,
    SkillsList,
    SubagentTextDelta,
    SubagentToolEnd,
    SubagentToolStart,
    TextDelta,
    TodosUpdated,
    TokenUsage,
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
        return {
            "type": "tool_start",
            "id": ev.id,
            "name": ev.name,
            "input": ev.input,
            "display": ev.display,
        }
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
            "display": ev.display,
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
    if isinstance(ev, SkillsList):
        return {"type": "skills_list", "skills": list(ev.skills)}
    if isinstance(ev, Cleared):
        return {"type": "cleared"}
    if isinstance(ev, TokenUsage):
        return {
            "type": "token_usage",
            "input_tokens": ev.input_tokens,
            "output_tokens": ev.output_tokens,
            "cache_read_tokens": ev.cache_read_tokens,
            "cache_creation_tokens": ev.cache_creation_tokens,
        }
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


async def _connect_stdin() -> asyncio.StreamReader:
    """Wrap sys.stdin in an async StreamReader so we can await lines while
    a turn is running concurrently."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    return reader


async def headless_loop(case: str, root: str) -> None:
    """Run the agent loop in headless mode, bridging stdin/stdout."""
    from ..agent import build_case_agent_components
    from ..observability import flush as _obs_flush
    from ..workspace import LocalFS

    ws = LocalFS(case_id=case, root=root)
    components = build_case_agent_components(ws)
    history: list[BaseMessage] = []

    # Advertise available commands + skills up-front so clients can populate
    # a slash picker. Body of each SKILL.md is loaded lazily via the `skill`
    # tool; commands run server-side via dispatch (see try_dispatch below).
    if components.commands or components.skills:
        _emit(build_skills_list_event(components.commands, components.skills))

    # One Langfuse session per stdio process — all turns roll up under it.
    chat_session_id = f"headless-{uuid.uuid4().hex[:12]}"
    print(
        f"[case-agent] langfuse session_id={chat_session_id}",
        file=sys.stderr,
        flush=True,
    )

    abort_event = asyncio.Event()
    run_task: asyncio.Task[None] | None = None

    async def run_turn(prompt: str, force_strategy: bool, abort: asyncio.Event) -> None:
        nonlocal history
        history.append(HumanMessage(content=prompt))
        async for ev in stream_query(
            prompt,
            components,
            messages=history,
            abort=abort,
            force_strategy=force_strategy,
            session_id=chat_session_id,
        ):
            _emit(ev)
            if isinstance(ev, Done):
                if ev.terminal.messages:
                    history = list(ev.terminal.messages)
                # Long-lived process: flush per turn so SIGINT can't lose data.
                _obs_flush()

    reader = await _connect_stdin()
    while True:
        line = await reader.readline()
        if not line:
            break  # EOF — parent closed stdin
        raw = line.decode(errors="replace").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"type": "error", "error": f"invalid json: {e}"}), flush=True)
            continue

        # Abort frame — signal the in-flight turn (if any).
        if payload.get("type") == "abort":
            abort_event.set()
            continue

        prompt: str = payload.get("prompt", "")
        force_strategy: bool = bool(payload.get("force_strategy", False))
        if not prompt:
            continue

        # Built-in command dispatch (e.g. /clear). Handler may abort the
        # in-flight turn, reset state, and return wire events to emit.
        async def _abort_in_flight() -> None:
            if run_task and not run_task.done():
                abort_event.set()
                try:
                    await run_task
                except Exception:  # noqa: BLE001
                    pass

        ctx = CommandContext(
            abort=_abort_in_flight,
            reset_history=lambda: history.clear(),
            reset_todos=lambda: components.todos_store.replace([]),
        )
        handled, events = await try_dispatch(prompt, components.commands, ctx)
        if handled:
            for ev in events:
                _emit(ev)
            continue

        prompt = expand_slash(prompt, components.skills)

        # Drop overlapping prompts — same policy as ws_server.
        if run_task and not run_task.done():
            print(
                json.dumps({"type": "error", "error": "turn in progress"}),
                flush=True,
            )
            continue

        abort_event = asyncio.Event()
        run_task = asyncio.create_task(run_turn(prompt, force_strategy, abort_event))

    # On EOF, wait for any in-flight turn to wind down so we don't truncate output.
    if run_task and not run_task.done():
        abort_event.set()
        try:
            await run_task
        except Exception:  # noqa: BLE001
            pass


__all__ = ["headless_loop"]
