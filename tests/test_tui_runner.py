"""AgentRunner translates StreamEvents from our loop into TUI tuples.

We bypass the heavy CaseAgentComponents/model stack by monkey-patching
``case_agent.tui.runner.stream_query`` so the test stays pure-async and
offline. The contract under test is: StreamEvent → TUI tuple mapping.
"""

from __future__ import annotations

import asyncio

import pytest

from case_agent.loop.types import (
    Done,
    Terminal,
    TextDelta,
    ToolEnd,
    ToolStart,
    TurnStart,
)
from case_agent.tui import runner as runner_mod
from case_agent.tui.runner import AgentRunner


def _make_runner(events: list) -> AgentRunner:
    async def _fake_stream(_prompt, _components, **_kwargs):  # noqa: ARG001
        for ev in events:
            yield ev

    runner_mod.stream_query = _fake_stream  # type: ignore[assignment]
    return AgentRunner(components=object())  # components unused in fake


def _collect(runner: AgentRunner) -> list[tuple]:
    async def go():
        return [t async for t in runner.stream("hi", thread_id="t")]

    return asyncio.run(go())


def test_text_deltas_become_token_tuples_in_order():
    events = [
        TurnStart(1),
        TextDelta("피고인은 "),
        TextDelta("홍길동"),
        TextDelta("입니다."),
        Done(Terminal("completed", final_text="피고인은 홍길동입니다.")),
    ]
    out = _collect(_make_runner(events))
    assert out == [
        ("token", "피고인은 "),
        ("token", "홍길동"),
        ("token", "입니다."),
        ("done",),
    ]


def test_empty_text_deltas_are_dropped():
    events = [
        TurnStart(1),
        TextDelta(""),
        TextDelta("hi"),
        Done(Terminal("completed", final_text="hi")),
    ]
    out = _collect(_make_runner(events))
    assert out == [("token", "hi"), ("done",)]


def test_tool_start_and_end_are_paired_by_id():
    events = [
        TurnStart(1),
        ToolStart("rid-1", "smart_search", {"query": "임의제출"}),
        ToolEnd("rid-1", {"hits": 3}, False),
        TurnStart(2),
        TextDelta("done"),
        Done(Terminal("completed", final_text="done")),
    ]
    out = _collect(_make_runner(events))
    starts = [t for t in out if t[0] == "tool_start"]
    ends = [t for t in out if t[0] == "tool_end"]
    assert len(starts) == 1 and starts[0][1] == "rid-1" and starts[0][2] == "smart_search"
    assert '"query": "임의제출"' in starts[0][3]
    assert ends[0][1] == "rid-1" and '"hits": 3' in ends[0][2]
    assert ends[0][3] is None  # no error
    assert out[-1] == ("done",)


def test_tool_error_carries_payload_in_error_slot():
    events = [
        TurnStart(1),
        ToolStart("rid-1", "flaky", {}),
        ToolEnd("rid-1", "RuntimeError: nope", True),
        Done(Terminal("completed", final_text="")),
    ]
    out = _collect(_make_runner(events))
    end = next(t for t in out if t[0] == "tool_end")
    assert end[3] is not None  # error slot populated
    assert "nope" in end[3]


def test_non_completed_terminal_appends_a_status_note():
    events = [
        TurnStart(1),
        TextDelta("partial"),
        Done(Terminal("max_turns")),
    ]
    out = _collect(_make_runner(events))
    # First token, then status note token, then done
    assert out[0] == ("token", "partial")
    assert out[1][0] == "token" and "max_turns" in out[1][1]
    assert out[-1] == ("done",)


def test_error_terminal_includes_message_in_status_note():
    events = [
        TurnStart(1),
        Done(Terminal("error", error="model 5xx")),
    ]
    out = _collect(_make_runner(events))
    note = next(t for t in out if t[0] == "token")
    assert "error" in note[1] and "model 5xx" in note[1]


def test_turn_start_events_are_silently_consumed():
    events = [
        TurnStart(1),
        TurnStart(2),
        TextDelta("ok"),
        Done(Terminal("completed", final_text="ok")),
    ]
    out = _collect(_make_runner(events))
    assert out == [("token", "ok"), ("done",)]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
