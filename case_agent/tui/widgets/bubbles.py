"""User and assistant message bubbles."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Markdown, Static

from .tool_block import ToolCallBlock


class _Bubble(Vertical):
    DEFAULT_CSS = """
    _Bubble {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
    }
    _Bubble > .role {
        color: $text-muted;
        text-style: bold;
    }
    """


class UserBubble(_Bubble):
    DEFAULT_CSS = """
    UserBubble {
        border-left: thick $primary;
    }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self):
        yield Static("you", classes="role")
        yield Markdown(self._text)


class AssistantBubble(_Bubble):
    """Streaming assistant turn. Holds a markdown body and inline tool blocks.

    Each tool call ends the current text segment so subsequent tokens land in a
    new Markdown widget mounted *below* the tool block — keeping the chat flow
    strictly append-only (newest content always at the bottom).
    """

    DEFAULT_CSS = """
    AssistantBubble {
        border-left: thick $success;
    }
    AssistantBubble > .footer {
        color: $warning;
        text-style: italic;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        # Active text segment: buffer + Markdown widget. Reset to None after
        # each tool_start so the next token spawns a fresh segment below.
        self._buffer: str = ""
        self._body: Markdown | None = None
        self._tool_blocks: dict[str, ToolCallBlock] = {}
        self._footer: Static | None = None

    def compose(self):
        yield Static("assistant", classes="role")

    async def append_token(self, text: str) -> None:
        if self._body is None:
            self._body = Markdown("")
            self._buffer = ""
            await self.mount(self._body)
            self._scroll_log_to_end()
        self._buffer += text
        self._body.update(self._buffer)

    async def add_tool_call(self, run_id: str, name: str, inputs: str) -> None:
        block = ToolCallBlock(run_id, name, inputs)
        self._tool_blocks[run_id] = block
        await self.mount(block)
        # Close the current text segment so post-tool tokens start a new one
        # mounted below this tool block.
        self._body = None
        self._buffer = ""
        self._scroll_log_to_end()

    def finish_tool_call(
        self, run_id: str, output: str, error: str | None = None
    ) -> None:
        block = self._tool_blocks.get(run_id)
        if block is not None:
            block.finish(output, error)

    async def mark_cancelled(self) -> None:
        if self._footer is None:
            self._footer = Static("[cancelled]", classes="footer", markup=False)
            await self.mount(self._footer)

    def _scroll_log_to_end(self) -> None:
        """Nudge the parent ChatLog to stick to the bottom after new mounts."""
        from .chat_log import ChatLog

        try:
            log = self.app.query_one(ChatLog)
        except Exception:  # noqa: BLE001 - app may be tearing down
            return
        log.call_after_refresh(log.scroll_end, animate=False)
