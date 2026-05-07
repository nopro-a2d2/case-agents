"""Tests for force_strategy plan-mode signal in stream_query()."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk, BaseMessage

from case_agent.loop.runner import stream_query
from case_agent.loop.strategy_mode import STRATEGY_FORCE_REMINDER


class _CapturingModel:
    """Stub that records the message list it receives, then ends the turn."""

    def __init__(self) -> None:
        self.captured: list[BaseMessage] | None = None

    def bind_tools(self, _tools):  # noqa: ARG002 — not exercised
        return self

    def astream(self, messages: Sequence[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        self.captured = list(messages)

        async def gen():
            yield AIMessageChunk(content="ok")

        return gen()


def _make_components(model: _CapturingModel) -> SimpleNamespace:
    return SimpleNamespace(
        workspace=None,
        model=model,
        tools=[],
        system_prompt="BASE_PROMPT",
        subagents={},
        todos_store=None,
    )


def _drain(prompt: str, components, *, force_strategy: bool) -> None:
    async def run() -> None:
        async for _ in stream_query(prompt, components, force_strategy=force_strategy):
            pass

    asyncio.run(run())


def test_force_strategy_appends_reminder_to_system_prompt() -> None:
    model = _CapturingModel()
    _drain("hi", _make_components(model), force_strategy=True)

    assert model.captured is not None
    sp = model.captured[0].content
    assert "BASE_PROMPT" in sp
    assert "<plan-mode-active>" in sp
    assert STRATEGY_FORCE_REMINDER in sp


def test_no_force_strategy_keeps_base_system_prompt() -> None:
    model = _CapturingModel()
    _drain("hi", _make_components(model), force_strategy=False)

    assert model.captured is not None
    sp = model.captured[0].content
    assert sp == "BASE_PROMPT"
    assert "<plan-mode-active>" not in sp


def test_default_is_off_when_flag_omitted() -> None:
    model = _CapturingModel()
    components = _make_components(model)

    async def run() -> None:
        async for _ in stream_query("hi", components):
            pass

    asyncio.run(run())

    assert model.captured is not None
    assert "<plan-mode-active>" not in model.captured[0].content


@pytest.mark.parametrize(
    "first, second, expect_first, expect_second",
    [
        (True, False, True, False),
        (False, True, False, True),
    ],
)
def test_toggle_does_not_pollute_subsequent_turns(
    first: bool, second: bool, expect_first: bool, expect_second: bool
) -> None:
    model = _CapturingModel()
    components = _make_components(model)

    _drain("turn1", components, force_strategy=first)
    sp_first = model.captured[0].content
    assert ("<plan-mode-active>" in sp_first) is expect_first

    _drain("turn2", components, force_strategy=second)
    sp_second = model.captured[0].content
    assert ("<plan-mode-active>" in sp_second) is expect_second
