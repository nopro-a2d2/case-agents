"""Unit tests for context caching wiring.

Covers:
- ``_build_system_message`` provider branching (Anthropic block-format with
  ``cache_control`` vs Gemini/stub plain str).
- ``_create_compile_cache`` graceful fallback (disabled flag, API failure).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import SystemMessage

from case_agent.loop.query import _build_system_message


class _StubModel:
    """Non-Anthropic, non-Gemini stub. Should get plain-str content."""


def test_build_system_message_stub_returns_plain_str() -> None:
    msg = _build_system_message(_StubModel(), "BASE", None)
    assert isinstance(msg, SystemMessage)
    assert msg.content == "BASE"


def test_build_system_message_stub_appends_extra() -> None:
    msg = _build_system_message(_StubModel(), "BASE", "EXTRA")
    assert msg.content == "BASE\n\nEXTRA"


def test_build_system_message_anthropic_uses_block_with_cache_control() -> None:
    """When the model is ChatAnthropicVertex, the helper emits a list of
    text blocks with ``cache_control`` on the static base prompt."""
    from case_agent.loop import query as query_mod

    if query_mod._ChatAnthropicVertex is None:
        pytest.skip("langchain_google_vertexai not importable in this env")

    fake = query_mod._ChatAnthropicVertex.__new__(query_mod._ChatAnthropicVertex)
    msg = _build_system_message(fake, "BASE", None)
    assert isinstance(msg.content, list)
    assert msg.content[0]["type"] == "text"
    assert msg.content[0]["text"] == "BASE"
    assert msg.content[0]["cache_control"] == {"type": "ephemeral"}


def test_build_system_message_anthropic_extra_is_uncached_block() -> None:
    from case_agent.loop import query as query_mod

    if query_mod._ChatAnthropicVertex is None:
        pytest.skip("langchain_google_vertexai not importable in this env")

    fake = query_mod._ChatAnthropicVertex.__new__(query_mod._ChatAnthropicVertex)
    msg = _build_system_message(fake, "BASE", "REMINDER")
    assert isinstance(msg.content, list)
    assert len(msg.content) == 2
    assert msg.content[0]["text"] == "BASE"
    assert "cache_control" in msg.content[0]
    assert msg.content[1]["text"] == "REMINDER"
    # Reminder block must NOT carry cache_control — keeps prefix stable.
    assert "cache_control" not in msg.content[1]


# --- wiki_builder _create_compile_cache fallback ---------------------------


@pytest.mark.asyncio
async def test_create_compile_cache_disabled_returns_none() -> None:
    from wiki_builder import realtime_compiler as rc

    client = SimpleNamespace(caches=SimpleNamespace(create=lambda **_: pytest.fail()))
    with patch.object(rc.wiki_settings, "ENABLE_PROMPT_CACHING", False):
        out = await rc._create_compile_cache(client)  # type: ignore[arg-type]
    assert out is None


@pytest.mark.asyncio
async def test_create_compile_cache_api_failure_returns_none(caplog) -> None:
    from wiki_builder import realtime_compiler as rc

    def _boom(**_kwargs):
        raise RuntimeError("token threshold not met")

    client = SimpleNamespace(caches=SimpleNamespace(create=_boom))
    with (
        patch.object(rc.wiki_settings, "ENABLE_PROMPT_CACHING", True),
        caplog.at_level("WARNING", logger="wiki_builder.realtime_compiler"),
    ):
        out = await rc._create_compile_cache(client)  # type: ignore[arg-type]
    assert out is None
    assert any("폴백" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_create_compile_cache_success_returns_handle() -> None:
    from wiki_builder import realtime_compiler as rc

    sentinel = SimpleNamespace(name="cachedContents/abc")

    def _ok(**_kwargs):
        return sentinel

    client = SimpleNamespace(caches=SimpleNamespace(create=_ok))
    with patch.object(rc.wiki_settings, "ENABLE_PROMPT_CACHING", True):
        out = await rc._create_compile_cache(client)  # type: ignore[arg-type]
    assert out is sentinel
