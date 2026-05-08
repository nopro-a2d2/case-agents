"""Verify that callbacks are threaded through query() into model.astream
and tool.ainvoke as ``config={"callbacks": [...]}``."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from case_agent.loop.query import query


_RECEIVED_CONFIGS: list[Any] = []


class _RecordingTool(BaseTool):
    """BaseTool subclass that records the ``config`` it was invoked with."""

    name: str = "search"
    description: str = "stub"

    def _run(self, query_text: str) -> str:  # noqa: ARG002
        return "hit"

    async def _arun(self, query_text: str) -> str:  # noqa: ARG002
        return "hit"

    async def ainvoke(self, input, config=None, **kwargs):  # noqa: A002
        _RECEIVED_CONFIGS.append(config)
        return await super().ainvoke(input, config=config, **kwargs)


class _RecordingModel:
    """Stub model that records the ``config`` kwarg of each astream call."""

    def __init__(self, turns: Sequence[Sequence[AIMessageChunk]]):
        self._turns = list(turns)
        self.astream_configs: list[Any] = []

    def bind_tools(self, _tools):  # noqa: ARG002
        return self

    def astream(
        self,
        messages: Sequence[BaseMessage],  # noqa: ARG002
        config: Any = None,
        **_kwargs,
    ) -> AsyncIterator[AIMessageChunk]:
        self.astream_configs.append(config)
        chunks = self._turns.pop(0)

        async def gen():
            for c in chunks:
                yield c

        return gen()


def _drain(model, tools=None, callbacks=None, metadata=None):
    async def _run():
        events = []
        async for ev in query(
            messages=[HumanMessage(content="hi")],
            system_prompt="sys",
            tools=tools or [],
            model=model,
            callbacks=callbacks,
            metadata=metadata,
        ):
            events.append(ev)
        return events

    return asyncio.run(_run())


def test_no_callbacks_means_no_config_kwarg():
    """When callbacks=None, astream is called without config — preserves stubs
    that don't accept the kwarg."""
    model = _RecordingModel([[AIMessageChunk(content="ok")]])
    _drain(model)
    # Recorded as the default (None) because we never pass config.
    assert model.astream_configs == [None]


def test_callbacks_threaded_into_model_astream_config():
    sentinel = object()
    model = _RecordingModel([[AIMessageChunk(content="ok")]])
    _drain(model, callbacks=[sentinel])

    assert len(model.astream_configs) == 1
    cfg = model.astream_configs[0]
    assert isinstance(cfg, dict)
    assert cfg.get("callbacks") == [sentinel]


def test_callbacks_propagate_to_tool_ainvoke():
    """Tool.ainvoke must receive the same RunnableConfig (callbacks) when set."""
    _RECEIVED_CONFIGS.clear()
    sentinel = object()
    tool = _RecordingTool()

    model = _RecordingModel(
        [
            [
                AIMessageChunk(
                    content="",
                    tool_calls=[
                        {"id": "t1", "name": "search", "args": {"query_text": "x"}, "type": "tool_call"},
                    ],
                ),
            ],
            [AIMessageChunk(content="done")],
        ]
    )
    _drain(model, tools=[tool], callbacks=[sentinel])

    assert len(_RECEIVED_CONFIGS) == 1
    assert _RECEIVED_CONFIGS[0] == {"callbacks": [sentinel]}


def test_metadata_threaded_into_model_astream_config():
    """Pass metadata=... → model.astream sees config={'metadata': {...}}.

    Mirrors how Langfuse's CallbackHandler picks up `langfuse_session_id`."""
    model = _RecordingModel([[AIMessageChunk(content="ok")]])
    md = {"langfuse_session_id": "s-1", "langfuse_tags": ["t1"]}
    _drain(model, metadata=md)

    assert len(model.astream_configs) == 1
    cfg = model.astream_configs[0]
    assert isinstance(cfg, dict)
    assert cfg.get("metadata") == md
    # No callbacks were passed → key should be absent.
    assert "callbacks" not in cfg


def test_metadata_inherited_by_subagent():
    """Sub-agent invocation must see the same metadata so its trace lands in
    the same Langfuse session as the parent."""
    from case_agent.loop.task_tool import StreamingTaskTool

    sub_model = _RecordingModel([[AIMessageChunk(content="sub-done")]])

    sub_agents = {
        "explore": {
            "name": "explore",
            "system_prompt": "sub",
            "tools": [],
            "model": sub_model,
            "description": "stub",
        }
    }
    task_tool = StreamingTaskTool(subagents=sub_agents, fallback_model=sub_model)

    main_model = _RecordingModel(
        [
            [
                AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "id": "t1",
                            "name": "task",
                            "args": {"subagent_name": "explore", "prompt": "go"},
                            "type": "tool_call",
                        },
                    ],
                ),
            ],
            [AIMessageChunk(content="parent-done")],
        ]
    )

    md = {"langfuse_session_id": "s-shared"}
    _drain(main_model, tools=[task_tool], metadata=md)

    # Main model saw it.
    assert main_model.astream_configs[0].get("metadata") == md
    # Sub-agent's recursive query() must have forwarded the same metadata.
    assert sub_model.astream_configs, "sub-agent never ran"
    assert sub_model.astream_configs[0].get("metadata") == md
