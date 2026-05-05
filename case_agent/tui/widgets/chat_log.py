"""Scrollable history of message bubbles."""

from __future__ import annotations

from textual.containers import VerticalScroll


class ChatLog(VerticalScroll):
    """Vertical scroll that auto-sticks to the bottom as new content arrives."""

    DEFAULT_CSS = """
    ChatLog {
        padding: 1 2;
    }
    """

    async def append(self, widget) -> None:
        await self.mount(widget)
        # Defer to the next refresh so layout has measured the new child.
        self.call_after_refresh(self.scroll_end, animate=False)
