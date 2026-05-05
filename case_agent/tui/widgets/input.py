"""Multi-line chat input. Enter submits, Shift+Enter inserts a newline."""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea


class ChatInput(TextArea):
    """TextArea that emits :class:`Submitted` on bare Enter."""

    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        max-height: 10;
        border: tall $accent;
    }
    """

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs) -> None:
        # show_line_numbers off, soft-wrap on by default
        super().__init__(language=None, **kwargs)
        self.show_line_numbers = False

    async def _on_key(self, event: events.Key) -> None:
        # Textual reports plain Enter as ``enter`` and Shift+Enter as
        # ``shift+enter`` - we only submit on the bare form.
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            value = self.text.strip()
            if value:
                self.text = ""
                self.post_message(self.Submitted(value))
