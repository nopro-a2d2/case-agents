"""Unit tests for the hand-rolled query() loop.

We feed a stub model that yields canned ``AIMessageChunk``s, plus tiny
LangChain ``BaseTool`` stubs, and assert the StreamEvent sequence and
final terminal match the claude-code stop_reason semantics we set out to
preserve.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.tools import StructuredTool

from case_agent.loop.query import query
from case_agent.loop.types import (
    Done,
    Terminal,
    TextDelta,
    ToolEnd,
    ToolStart,
    TurnStart,
)


# ---------------------------------------------------------------- stubs


class _StubModel:
    """Yield a pre-canned list of AIMessageChunk lists, one per turn."""

    def __init__(self, turns: Sequence[Sequence[AIMessageChunk]]):
        self._turns = list(turns)
        self.calls: list[list[BaseMessage]] = []

    def bind_tools(self, _tools):  # noqa: ARG002 — tool schemas not exercised here
        return self

    def astream(self, messages: Sequence[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        # Snapshot the messages the loop sent us this turn.
        self.calls.append(list(messages))
        chunks = self._turns.pop(0)

        async def gen():
            for c in chunks:
                yield c

        return gen()


def _text_chunk(text: str) -> AIMessageChunk:
    return AIMessageChunk(content=text)


def _tool_chunk(*, tc_id: str, name: str, args: dict[str, Any]) -> AIMessageChunk:
    """An AIMessageChunk that carries a single tool_call.

    LangChain populates ``tool_calls`` from ``additional_kwargs`` /
    ``tool_call_chunks`` depending on the provider; we set ``tool_calls``
    directly because that's what the loop reads after fold.
    """
    return AIMessageChunk(content="", tool_calls=[
        {"id": tc_id, "name": name, "args": args, "type": "tool_call"},
    ])


def _make_tool(name: str, fn):
    return StructuredTool.from_function(
        coroutine=fn,
        name=name,
        description=f"stub {name}",
    )


def _collect(coro):
    return asyncio.run(coro)


async def _drain(*, model, tools, system="sys", max_turns=5, abort=None):
    from langchain_core.messages import HumanMessage

    events = []
    async for ev in query(
        messages=[HumanMessage(content="hi")],
        system_prompt=system,
        tools=tools,
        model=model,
        max_turns=max_turns,
        abort=abort,
    ):
        events.append(ev)
    return events


# ----------------------------------------------------------------- tests


def test_end_turn_returns_completed_with_final_text():
    """A model that emits text and no tool_call must complete cleanly."""
    model = _StubModel([[_text_chunk("피고인은 "), _text_chunk("홍길동입니다.")]])
    events = _collect(_drain(model=model, tools=[]))

    assert isinstance(events[0], TurnStart) and events[0].turn == 1
    text_deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert text_deltas == ["피고인은 ", "홍길동입니다."]
    assert isinstance(events[-1], Done)
    assert events[-1].terminal == Terminal("completed", final_text="피고인은 홍길동입니다.")


def test_tool_use_then_end_turn_appends_tool_message_and_continues():
    """Turn 1 emits tool_use; tool runs; turn 2 emits text → completed."""
    seen_args: dict[str, Any] = {}

    async def search(query: str) -> str:
        seen_args["query"] = query
        return '{"hits": ["피고인=홍길동"]}'

    tool = _make_tool("smart_search", search)

    model = _StubModel([
        [_tool_chunk(tc_id="t1", name="smart_search", args={"query": "피고인"})],
        [_text_chunk("피고인은 홍길동입니다.")],
    ])
    events = _collect(_drain(model=model, tools=[tool]))

    starts = [e for e in events if isinstance(e, ToolStart)]
    ends = [e for e in events if isinstance(e, ToolEnd)]
    assert len(starts) == 1 and starts[0].name == "smart_search"
    assert seen_args == {"query": "피고인"}
    assert ends[0].is_error is False

    # Turn 2 must have received an extra ToolMessage in its input.
    second_call = model.calls[1]
    assert second_call[-1].type == "tool"
    assert second_call[-1].tool_call_id == "t1"
    assert "홍길동" in second_call[-1].content

    assert isinstance(events[-1], Done)
    assert events[-1].terminal.reason == "completed"
    assert events[-1].terminal.final_text == "피고인은 홍길동입니다."


def test_tool_error_is_fed_back_as_error_tool_message():
    async def boom(arg: str) -> str:  # noqa: ARG001 — only need a valid signature
        raise RuntimeError("index missing")

    tool = _make_tool("flaky", boom)
    model = _StubModel([
        [_tool_chunk(tc_id="t1", name="flaky", args={"arg": "x"})],
        [_text_chunk("ok, 다른 방법으로 답합니다.")],
    ])
    events = _collect(_drain(model=model, tools=[tool]))

    end = next(e for e in events if isinstance(e, ToolEnd))
    assert end.is_error is True
    assert "index missing" in str(end.output)

    second_call = model.calls[1]
    assert second_call[-1].type == "tool"
    # status="error" → the message is_error=True for Anthropic serialization
    assert second_call[-1].status == "error"


def test_unknown_tool_name_yields_error_without_raising():
    model = _StubModel([
        [_tool_chunk(tc_id="t1", name="ghost", args={})],
        [_text_chunk("done")],
    ])
    events = _collect(_drain(model=model, tools=[]))
    end = next(e for e in events if isinstance(e, ToolEnd))
    assert end.is_error is True
    assert "unknown tool" in str(end.output)


def test_max_turns_terminates_when_model_keeps_calling_tools():
    async def echo(arg: str) -> str:  # noqa: ARG001
        return "ok"

    tool = _make_tool("echo", echo)
    # 3 turns each emitting tool_use with no end_turn → should hit cap of 2.
    model = _StubModel(
        [[_tool_chunk(tc_id=f"t{i}", name="echo", args={"arg": "x"})] for i in range(5)]
    )
    events = _collect(_drain(model=model, tools=[tool], max_turns=2))
    assert isinstance(events[-1], Done)
    assert events[-1].terminal.reason == "max_turns"


def test_abort_event_stops_before_next_turn():
    async def echo(arg: str) -> str:  # noqa: ARG001
        return "ok"

    tool = _make_tool("echo", echo)
    abort = asyncio.Event()
    abort.set()  # already aborted before turn 1 even runs

    model = _StubModel([[_text_chunk("never reached")]])
    events = _collect(_drain(model=model, tools=[tool], abort=abort))
    assert events == [Done(Terminal("aborted"))]


def test_final_text_is_empty_for_pure_tool_use_then_end():
    """Turn 1: tool_use only. Turn 2: empty text + no tool. Should still complete."""

    async def search(q: str) -> str:  # noqa: ARG001
        return "[]"

    tool = _make_tool("s", search)
    model = _StubModel([
        [_tool_chunk(tc_id="t1", name="s", args={"q": "x"})],
        [_text_chunk("")],
    ])
    events = _collect(_drain(model=model, tools=[tool]))
    assert isinstance(events[-1], Done)
    assert events[-1].terminal.reason == "completed"
    assert events[-1].terminal.final_text == ""


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
