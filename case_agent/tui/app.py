"""Textual chat app for case-agent.

Launch with :func:`launch_chat`; the CLI wires this up when ``case-agent
run --case <id>`` is invoked without a prompt argument.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, ListItem, ListView, Static

from ..workspace import LocalFS
from .runner import AgentRunner
from .sessions import DEFAULT_SESSION, SessionStore
from .widgets import AssistantBubble, ChatInput, ChatLog, UserBubble


class _SessionPickerScreen(ModalScreen[str | None]):
    """Modal listing saved sessions; Enter switches, Esc cancels."""

    BINDINGS = [Binding("escape", "dismiss(None)", "cancel")]

    DEFAULT_CSS = """
    _SessionPickerScreen {
        align: center middle;
    }
    _SessionPickerScreen > Container {
        width: 60;
        max-height: 20;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    """

    def __init__(self, store: SessionStore, current: str) -> None:
        super().__init__()
        self.store = store
        self.current = current

    def compose(self) -> ComposeResult:
        with Container():
            yield Static("Sessions  (Enter to switch, Esc to cancel)")
            items: list[ListItem] = []
            for meta in self.store.list_sessions():
                marker = "● " if meta.name == self.current else "  "
                preview = meta.preview[:40] if meta.preview else "(empty)"
                item = ListItem(Static(f"{marker}{meta.name}  —  {preview}"))
                item.session_name = meta.name  # type: ignore[attr-defined]
                items.append(item)
            yield ListView(*items, id="session-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        name = getattr(event.item, "session_name", None)
        self.dismiss(name)


class ChatApp(App):
    """Top-level Textual chat application."""

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit_app", "quit"),
        Binding("ctrl+n", "new_session", "new"),
        Binding("ctrl+l", "list_sessions", "sessions"),
        Binding("ctrl+c", "cancel_or_quit", "cancel/quit"),
        Binding("ctrl+t", "toggle_theme", "theme"),
    ]

    def __init__(
        self,
        *,
        case: str,
        root: str,
        session: str | None = None,
        theme: str | None = None,
    ) -> None:
        super().__init__()
        self.theme = theme or "textual-light"
        self.case = case
        self.root = root
        self.session = session or DEFAULT_SESSION
        ws = LocalFS(case_id=case, root=root)
        self.workspace = ws
        self.store = SessionStore(Path(ws.case_root))
        self.store.checkpointer.setup()
        self._runner: AgentRunner | None = None  # built lazily inside the loop
        self._current_bubble: AssistantBubble | None = None
        self._stream_worker = None

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield ChatLog(id="chat-log")
        yield ChatInput(id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_title()
        self.query_one(ChatInput).focus()

    def _refresh_title(self) -> None:
        self.title = "case-agent"
        self.sub_title = f"case={self.case}  session={self.session}"

    # ------------------------------------------------------------------ runner

    async def _ensure_runner(self) -> AgentRunner:
        if self._runner is None:
            from ..agent import build_case_agent_components  # heavy import deferred

            components = build_case_agent_components(self.workspace)
            self._runner = AgentRunner(components)
        return self._runner

    # ------------------------------------------------------------------ events

    async def on_chat_input_submitted(self, message: ChatInput.Submitted) -> None:
        text = message.value
        if text.startswith("/"):
            await self._handle_slash(text)
            return
        await self._send(text)

    async def _send(self, text: str) -> None:
        log = self.query_one(ChatLog)
        await log.append(UserBubble(text))
        bubble = AssistantBubble()
        self._current_bubble = bubble
        await log.append(bubble)
        self.store.touch(self.session, preview=text[:80])
        self._stream_worker = self._stream_agent(text, bubble)

    @work(exclusive=True, group="agent")
    async def _stream_agent(self, prompt: str, bubble: AssistantBubble) -> None:
        runner = await self._ensure_runner()
        try:
            async for ev in runner.stream(prompt, thread_id=self.session):
                kind = ev[0]
                if kind == "token":
                    await bubble.append_token(ev[1])
                elif kind == "tool_start":
                    _, run_id, name, inputs = ev
                    await bubble.add_tool_call(run_id, name, inputs)
                elif kind == "tool_end":
                    _, run_id, output, error = ev
                    bubble.finish_tool_call(run_id, output, error)
                elif kind == "done":
                    break
        except Exception as exc:  # noqa: BLE001 - surface to user
            await bubble.append_token(f"\n\n_error: {exc!s}_")
        finally:
            self._current_bubble = None

    # ------------------------------------------------------------------ slash

    async def _handle_slash(self, raw: str) -> None:
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) == 2 else ""
        if cmd == "/quit":
            await self.action_quit_app()
        elif cmd == "/new":
            await self._switch_to(arg or self._next_session_name())
        elif cmd == "/sessions":
            await self.action_list_sessions()
        elif cmd == "/clear":
            self.store.delete(self.session)
            await self._reload_log()
        else:
            log = self.query_one(ChatLog)
            await log.append(UserBubble(f"_unknown command: `{cmd}`_"))

    def _next_session_name(self) -> str:
        existing = {m.name for m in self.store.list_sessions()}
        i = 1
        while f"session-{i}" in existing:
            i += 1
        return f"session-{i}"

    async def _switch_to(self, name: str) -> None:
        self.session = name
        self.store.touch(name)
        self._refresh_title()
        await self._reload_log()

    async def _reload_log(self) -> None:
        # We don't replay the full conversation; LangGraph's checkpointer
        # restores agent state, so the next user turn continues correctly.
        # Just clear the visible bubbles to give a clean canvas.
        log = self.query_one(ChatLog)
        await log.remove_children()

    # ------------------------------------------------------------------ actions

    async def action_quit_app(self) -> None:
        if self._stream_worker is not None:
            self._stream_worker.cancel()
        await self.store.aclose()
        self.exit()

    async def action_new_session(self) -> None:
        await self._switch_to(self._next_session_name())

    async def action_list_sessions(self) -> None:
        picked = await self.push_screen_wait(
            _SessionPickerScreen(self.store, self.session)
        )
        if picked and picked != self.session:
            await self._switch_to(picked)

    async def action_cancel_or_quit(self) -> None:
        if self._stream_worker is not None and self._current_bubble is not None:
            self._stream_worker.cancel()
            await self._current_bubble.mark_cancelled()
            self._stream_worker = None
            return
        await self.action_quit_app()

    def action_toggle_theme(self) -> None:
        """Flip between Textual's default light and dark themes."""
        self.theme = (
            "textual-dark" if str(self.theme).endswith("-light") else "textual-light"
        )


def launch_chat(
    *,
    case: str,
    root: str,
    session: str | None = None,
    theme: str | None = None,
) -> None:
    """Blocking entry point used by the CLI."""
    ChatApp(case=case, root=root, session=session, theme=theme).run()
