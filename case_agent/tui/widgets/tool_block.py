"""Collapsible block showing one tool call's inputs and outputs."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Collapsible, Static


class ToolCallBlock(Vertical):
    """One inline tool-call card inside an assistant turn."""

    DEFAULT_CSS = """
    ToolCallBlock {
        height: auto;
        margin: 1 0 0 0;
    }
    ToolCallBlock > Collapsible {
        background: $boost;
        border: round $accent;
    }
    ToolCallBlock .tool-input,
    ToolCallBlock .tool-output {
        padding: 0 1;
    }
    ToolCallBlock .tool-output.error {
        color: $error;
    }
    """

    def __init__(self, run_id: str, name: str, inputs: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.tool_name = name
        self._inputs = inputs
        self._collapsible: Collapsible | None = None
        self._output_static: Static | None = None

    def compose(self):
        # Default open while running; we collapse it once the result arrives.
        self._collapsible = Collapsible(
            title=f"🔧 {self.tool_name}  (running…)",
            collapsed=False,
        )
        with self._collapsible:
            yield Static(
                f"input:\n{self._inputs}", classes="tool-input", markup=False
            )
            self._output_static = Static(
                "output: …", classes="tool-output", markup=False
            )
            yield self._output_static
        yield self._collapsible

    def finish(self, output: str, error: str | None = None) -> None:
        if self._output_static is None or self._collapsible is None:
            return
        if error:
            self._output_static.update(f"error:\n{error}")
            self._output_static.add_class("error")
            self._collapsible.title = f"🔧 {self.tool_name}  (failed)"
        else:
            self._output_static.update(f"output:\n{output}")
            self._collapsible.title = f"🔧 {self.tool_name}"
            self._collapsible.collapsed = True
