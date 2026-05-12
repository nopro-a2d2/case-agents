"""Async query() generator — the explicit while-loop modeled on
``claude-code/query.ts:241-394``.

Mapping (claude-code → here):
  - ``while(true) { ... }``                    → ``for turn in range(1, max_turns+1)``
  - per-iteration ``call_model``               → ``model.bind_tools(tools).astream(messages)``
  - ``stop_reason == "tool_use"`` branch       → ``if assistant_msg.tool_calls:``
  - ``stop_reason == "end_turn"`` branch       → ``else: yield Done(completed)``
  - tool_result content blocks                 → ``ToolMessage(...)`` accumulation
  - ``abortController.signal.aborted``         → ``asyncio.Event`` poll

We stay on LangChain ``BaseMessage`` types end-to-end so
``ChatAnthropicVertex`` and ``BaseTool`` plug in with no shimming.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, Callable

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

try:
    from langchain_google_vertexai.model_garden import (
        ChatAnthropicVertex as _ChatAnthropicVertex,
    )
except ImportError:  # pragma: no cover — minimal test env
    _ChatAnthropicVertex = None  # type: ignore[assignment]

from case_agent.loop.types import (
    Done,
    StreamEvent,
    SubagentTextDelta,
    SubagentToolEnd,
    SubagentToolStart,
    Terminal,
    TextDelta,
    TodosUpdated,
    TokenUsage,
    ToolEnd,
    ToolStart,
    TurnStart,
    coerce_text,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

    from case_agent.guardrails import GuardrailManager
    from case_agent.tools.todos import TodoStore


DEFAULT_MAX_TURNS = 25

_GUARDRAIL_REFUSAL = (
    "저는 AiLex AI 입니다. 해당 요청은 답변드릴 수 없습니다. "
    "사건 분석·QA·서면 작성과 관련된 질문을 도와드릴게요."
)


def _build_system_message(
    model: "BaseChatModel",
    base_prompt: str,
    extra: str | None = None,
) -> SystemMessage:
    """Build the leading SystemMessage for the loop.

    For Anthropic (Claude) models we emit a structured-block content with a
    ``cache_control`` marker on the static base prompt, enabling 5-minute
    ephemeral prompt caching across turns. ``extra`` (e.g. the strategy
    reminder) is sent as a separate, uncached block so it can change per turn
    without invalidating the prefix cache.

    For non-Anthropic models we emit plain text — the providers' own implicit
    caching applies, and stub models in tests keep their simple ``str``
    contract.
    """
    is_anthropic = (
        _ChatAnthropicVertex is not None
        and isinstance(model, _ChatAnthropicVertex)
    )
    if not is_anthropic:
        text = f"{base_prompt}\n\n{extra}" if extra else base_prompt
        return SystemMessage(content=text)
    blocks: list[dict] = [
        {
            "type": "text",
            "text": base_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if extra:
        blocks.append({"type": "text", "text": extra})
    return SystemMessage(content=blocks)


async def query(
    *,
    messages: Sequence[BaseMessage],
    system_prompt: str,
    tools: list["BaseTool"],
    model: "BaseChatModel",
    max_turns: int = DEFAULT_MAX_TURNS,
    abort: asyncio.Event | None = None,
    stream_timeout: float | None = None,
    todos_store: "TodoStore | None" = None,
    callbacks: list | None = None,
    metadata: dict | None = None,
    system_extra: str | None = None,
    display_label_fn: Callable[[str, dict], "dict | None"] | None = None,
    guardrails: "GuardrailManager | None" = None,
) -> AsyncIterator[StreamEvent]:
    """Run the LLM↔Tool loop until end_turn, max_turns, or abort.

    Args:
        messages: initial conversation (typically ``[HumanMessage(prompt)]``).
            A ``SystemMessage`` is prepended automatically.
        system_prompt: system text. Goes in front of ``messages``.
        tools: LangChain ``BaseTool`` list. Bound to the model each turn.
        model: a ``BaseChatModel`` supporting ``bind_tools`` + ``astream``.
        max_turns: hard upper bound on iterations (claude-code's turnCount cap).
        abort: optional asyncio Event; checked at the top of every turn.
        callbacks: optional LangChain callback list (e.g. Langfuse handler).
            When non-empty, threaded into ``model.astream`` and ``tool.ainvoke``
            via ``RunnableConfig`` so observability spans nest automatically.

    Yields:
        ``StreamEvent``s in order: TurnStart → TextDelta* → ToolStart/ToolEnd*
        → ... → Done. ``Done`` is always the last event.
    """
    state: list[BaseMessage] = [
        _build_system_message(model, system_prompt, system_extra),
        *messages,
    ]
    model_with_tools = model.bind_tools(tools) if tools else model
    tools_by_name = {t.name: t for t in tools}

    # Only build a config dict when we actually have callbacks or metadata —
    # keeps the call signature unchanged for existing stub models in tests.
    run_config: dict | None = None
    if callbacks or metadata:
        run_config = {}
        if callbacks:
            run_config["callbacks"] = callbacks
        if metadata:
            run_config["metadata"] = metadata
    stream_kwargs = {"config": run_config} if run_config else {}

    # Before-agent guardrails — run once on the entry prompt.
    if guardrails is not None:
        from case_agent.guardrails import Verdict as _Verdict

        decision = await guardrails.before_agent(messages, system_prompt)
        if decision.verdict is _Verdict.BLOCK:
            text = decision.replacement or _GUARDRAIL_REFUSAL
            # TurnStart MUST precede TextDelta — the web/TUI client only
            # creates its assistant bubble on turn_start(turn=1), so dropping
            # this event would make the refusal invisible.
            yield TurnStart(1)
            yield TextDelta(text)
            blocked = AIMessage(content=text)
            yield Done(
                Terminal(
                    "completed",
                    final_text=text,
                    messages=tuple([*messages, blocked]),
                )
            )
            return

    for turn in range(1, max_turns + 1):
        if abort is not None and abort.is_set():
            yield Done(Terminal("aborted", messages=tuple(state[1:])))
            return

        yield TurnStart(turn)

        # 1. Stream the assistant turn — accumulate chunks via __add__ fold.
        accumulated: AIMessageChunk | None = None
        try:
            cm = asyncio.timeout(stream_timeout) if stream_timeout is not None else contextlib.nullcontext()
            async with cm:
                async for chunk in model_with_tools.astream(state, **stream_kwargs):
                    if not isinstance(chunk, AIMessageChunk):
                        # Some adapters yield a final AIMessage as the last chunk;
                        # cast to chunk so the fold stays homogeneous.
                        chunk = AIMessageChunk(  # type: ignore[assignment]
                            content=getattr(chunk, "content", ""),
                            additional_kwargs=getattr(chunk, "additional_kwargs", {}),
                        )
                    accumulated = chunk if accumulated is None else accumulated + chunk
                    delta = coerce_text(chunk.content)
                    if delta:
                        yield TextDelta(delta)
        except asyncio.TimeoutError:
            yield Done(Terminal("error", error="model stream timed out", messages=tuple(state[1:])))
            return
        except Exception as e:  # noqa: BLE001 — surface any model error to caller
            yield Done(Terminal("error", error=f"{type(e).__name__}: {e}", messages=tuple(state[1:])))
            return

        if accumulated is None:
            yield Done(Terminal("error", error="model produced no chunks", messages=tuple(state[1:])))
            return

        assistant_msg = AIMessage(
            content=accumulated.content,
            tool_calls=list(accumulated.tool_calls or []),
            additional_kwargs=dict(accumulated.additional_kwargs or {}),
            response_metadata=dict(accumulated.response_metadata or {}),
        )
        state.append(assistant_msg)

        usage = getattr(accumulated, "usage_metadata", None) or {}
        if usage:
            details = usage.get("input_token_details") or {}
            yield TokenUsage(
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                cache_read_tokens=int(details.get("cache_read") or 0),
                cache_creation_tokens=int(details.get("cache_creation") or 0),
            )

        # 2. stop_reason branch.
        if not assistant_msg.tool_calls:
            final_text = coerce_text(assistant_msg.content)
            if guardrails is not None:
                from case_agent.guardrails import Verdict as _Verdict

                decision = await guardrails.after_agent(state[1:], final_text)
                if decision.verdict is _Verdict.BLOCK:
                    replacement = decision.replacement or _GUARDRAIL_REFUSAL
                    yield TextDelta("\n\n" + replacement)
                    final_text = replacement
                    # Replace the assistant turn so downstream history reflects
                    # the sanitised response.
                    state[-1] = AIMessage(content=replacement)
            yield Done(Terminal("completed", final_text=final_text, messages=tuple(state[1:])))
            return

        # 3. Execute each tool_use → append ToolMessage(s).
        for tc in assistant_msg.tool_calls:
            tc_id = tc.get("id") or str(uuid.uuid4())
            tc_name = tc.get("name") or ""
            tc_args = tc.get("args") or {}
            display = None
            if display_label_fn is not None:
                try:
                    display = display_label_fn(tc_name, dict(tc_args))
                except Exception:
                    display = None
            yield ToolStart(tc_id, tc_name, dict(tc_args), display)

            tool = tools_by_name.get(tc_name)
            if tool is None:
                err = f"unknown tool: {tc_name!r}"
                state.append(
                    ToolMessage(content=err, tool_call_id=tc_id, status="error")
                )
                yield ToolEnd(tc_id, err, True)
                continue

            todos_before = (
                tuple(todos_store.snapshot()) if todos_store is not None else None
            )
            try:
                if hasattr(tool, "_arun_streaming"):
                    # StreamingTaskTool: bubble subagent events up to the TUI.
                    # Forward callbacks so the sub-agent's spans nest under
                    # this trace.
                    output = ""
                    async for sub_ev in tool._arun_streaming(
                        **tc_args,
                        _callbacks=callbacks,
                        _metadata=metadata,
                        _display_label_fn=display_label_fn,
                    ):
                        if isinstance(sub_ev, TextDelta) and sub_ev.text:
                            yield SubagentTextDelta(tc_id, sub_ev.text)
                        elif isinstance(sub_ev, ToolStart):
                            yield SubagentToolStart(
                                tc_id, sub_ev.id, sub_ev.name, sub_ev.input, sub_ev.display
                            )
                        elif isinstance(sub_ev, ToolEnd):
                            yield SubagentToolEnd(tc_id, sub_ev.id, sub_ev.output, sub_ev.is_error)
                        elif isinstance(sub_ev, Done):
                            output = sub_ev.terminal.final_text or ""
                            if sub_ev.terminal.reason == "error":
                                output = f"subagent error: {sub_ev.terminal.error}"
                            elif sub_ev.terminal.reason != "completed":
                                output = f"subagent stopped: reason={sub_ev.terminal.reason}"
                else:
                    if run_config is not None:
                        output = await tool.ainvoke(tc_args, config=run_config)
                    else:
                        output = await tool.ainvoke(tc_args)
                state.append(
                    ToolMessage(
                        content=_stringify_tool_output(output),
                        tool_call_id=tc_id,
                    )
                )
                yield ToolEnd(tc_id, output, False)
                if todos_store is not None:
                    todos_after = tuple(todos_store.snapshot())
                    if todos_after != todos_before:
                        yield TodosUpdated(todos=todos_after)
            except Exception as e:  # noqa: BLE001 — feed error back to the model
                err = f"{type(e).__name__}: {e}"
                state.append(
                    ToolMessage(content=err, tool_call_id=tc_id, status="error")
                )
                yield ToolEnd(tc_id, err, True)
        # 4. continue → next iteration calls the model with the appended results.

    yield Done(Terminal("max_turns", messages=tuple(state[1:])))


def _stringify_tool_output(output: Any) -> str:
    """Tools wrapped with @tool already return strings. Be defensive for
    callers that hand back BaseModel/dict/list — Anthropic's tool_result
    content must be a string (or list of blocks; we keep it simple)."""
    if isinstance(output, str):
        return output
    if hasattr(output, "model_dump_json"):  # pydantic v2
        try:
            return output.model_dump_json()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(output, "json"):  # pydantic v1 fallback
        try:
            return output.json()
        except Exception:  # noqa: BLE001
            pass
    try:
        import json

        return json.dumps(output, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return repr(output)


def initial_messages(prompt: str) -> list[BaseMessage]:
    """Convenience: wrap a single user prompt in the LangChain message list."""
    return [HumanMessage(content=prompt)]


__all__ = ["DEFAULT_MAX_TURNS", "initial_messages", "query"]
