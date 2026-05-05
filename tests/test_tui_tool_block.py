"""Regression: ToolCallBlock must render JSON tool I/O containing '[' verbatim.

Textual's `Static` widget defaults to parsing Rich console markup, which trips
on JSON output (e.g. the `trace` array returned by `smart_search`). The bug
surfaced as `MarkupError: Expected markup value (found '-embeding-2)",\n
"cache: registries loaded')` when the user asked the agent a question that
exercised the search tool.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from case_agent.tui.widgets.tool_block import ToolCallBlock


_JSON_WITH_BRACKETS = (
    '{\n'
    '  "trace": [\n'
    '    "wiki-embeddings: 5 seed hits (model=gemini-embedding-2)",\n'
    '    "cache: registries loaded; ids resolvable for drill-down"\n'
    '  ]\n'
    '}'
)


class _Harness(App):
    def __init__(self, block: ToolCallBlock) -> None:
        super().__init__()
        self._block = block

    def compose(self) -> ComposeResult:
        yield self._block


@pytest.mark.asyncio
async def test_tool_block_renders_json_output_without_markup_error() -> None:
    block = ToolCallBlock(run_id="r1", name="smart_search", inputs='{"q": "x"}')
    app = _Harness(block)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause()
        # The bug fires when Static.update is rendered, not at construction.
        block.finish(_JSON_WITH_BRACKETS)
        await pilot.pause()


@pytest.mark.asyncio
async def test_tool_block_renders_json_input_without_markup_error() -> None:
    # Same hazard, but on the input side.
    block = ToolCallBlock(run_id="r2", name="smart_search", inputs=_JSON_WITH_BRACKETS)
    app = _Harness(block)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause()


@pytest.mark.asyncio
async def test_tool_block_renders_error_payload_without_markup_error() -> None:
    block = ToolCallBlock(run_id="r3", name="smart_search", inputs="{}")
    app = _Harness(block)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause()
        block.finish(output="", error=_JSON_WITH_BRACKETS)
        await pilot.pause()
