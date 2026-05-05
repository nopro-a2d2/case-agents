"""Live end-to-end TUI smoke test.

Drives :class:`ChatApp` headlessly with Textual's :class:`Pilot`, sends one
short prompt, and asserts that:
  * a UserBubble and AssistantBubble are mounted into the chat log,
  * the assistant streamed at least one token, and
  * a session row exists in ``index.json`` after the turn.

Skips when GCP credentials are absent. Otherwise hits the real Vertex
backend - keep the prompt tiny.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

REQUIRED = ("GCP_PROJECT", "VERTEX_LOCATION", "GOOGLE_APPLICATION_CREDENTIALS")

# Load .env before the skip check so credentials configured in the project
# root are picked up the same way ``case-agent run`` does.
from case_agent._env import load_env  # noqa: E402

load_env()

pytestmark = pytest.mark.skipif(
    not all(os.environ.get(k) for k in REQUIRED),
    reason="needs GCP_PROJECT + VERTEX_LOCATION + GOOGLE_APPLICATION_CREDENTIALS",
)


@pytest.mark.asyncio
async def test_simple_query_streams_into_assistant_bubble() -> None:
    from case_agent.tui.app import ChatApp
    from case_agent.tui.widgets import AssistantBubble, ChatInput, ChatLog, UserBubble

    src = Path("data/spark")
    assert src.exists(), "spark case data missing"
    with tempfile.TemporaryDirectory() as tmp:
        # Copy enough of the case for the agent to boot. Keep it small: we
        # don't actually need the full corpus for a one-token reply.
        case_dir = Path(tmp) / "spark"
        case_dir.mkdir()
        for sub in ("json", "txt", "wiki-output", "cache", "sources"):
            s = src / sub
            if s.exists():
                shutil.copytree(s, case_dir / sub)

        app = ChatApp(case="spark", root=tmp, session="smoke")
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            log = app.query_one(ChatLog)
            chat_input = app.query_one(ChatInput)

            chat_input.text = "Reply with the single word: pong"
            await pilot.press("enter")
            await pilot.pause()

            # Wait up to 60s for the worker group to finish.
            for _ in range(120):
                if not app.workers._workers:
                    break
                await pilot.pause(0.5)

            users = list(log.query(UserBubble))
            bots = list(log.query(AssistantBubble))
            assert len(users) == 1, "user bubble missing"
            assert len(bots) == 1, "assistant bubble missing"
            assert bots[0]._buffer.strip(), (
                f"assistant bubble has no streamed tokens; got {bots[0]._buffer!r}"
            )

        sessions = (case_dir / "sessions" / "index.json").read_text(encoding="utf-8")
        assert "smoke" in sessions
