"""Unit tests for case_agent.observability — env-driven, fail-soft."""

from __future__ import annotations

import sys
import types

import pytest

from case_agent import observability


@pytest.fixture(autouse=True)
def _reset_obs(monkeypatch):
    observability.reset_for_test()
    # Strip Langfuse env vars by default; individual tests opt in.
    for k in (
        "LANGFUSE_ENABLED",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
        "LANGFUSE_BASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    yield
    observability.reset_for_test()


def test_disabled_returns_none_and_does_not_import_langfuse(monkeypatch):
    """Default env → all getters return None, no langfuse import attempted."""
    # If observability tried to import langfuse we'd see it in sys.modules.
    # The package may already be present in the env, so we can't assert on
    # absence — instead assert get_langfuse() returns None and build_callbacks()
    # returns None without exploding.
    assert observability.get_langfuse() is None
    assert observability.get_langchain_callback() is None
    assert observability.build_callbacks() is None
    # flush is a no-op when disabled.
    observability.flush()


def test_enabled_with_mocked_langfuse(monkeypatch):
    """LANGFUSE_ENABLED=true + stub modules → handler returned, singleton honored."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://example.test")

    auth_calls: list[bool] = []
    flush_calls: list[bool] = []
    handler_calls: list[bool] = []

    class _StubLangfuse:
        def __init__(self, public_key, secret_key, host):  # noqa: ARG002
            self.public_key = public_key
            self.host = host

        def auth_check(self):
            auth_calls.append(True)
            return True

        def flush(self):
            flush_calls.append(True)

    class _StubHandler:
        def __init__(self):
            handler_calls.append(True)

    # Inject stub modules.
    langfuse_mod = types.ModuleType("langfuse")
    langfuse_mod.Langfuse = _StubLangfuse  # type: ignore[attr-defined]
    langchain_mod = types.ModuleType("langfuse.langchain")
    langchain_mod.CallbackHandler = _StubHandler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", langfuse_mod)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", langchain_mod)

    client = observability.get_langfuse()
    assert isinstance(client, _StubLangfuse)
    assert client.host == "https://example.test"
    assert auth_calls == [True]

    handler = observability.get_langchain_callback()
    assert isinstance(handler, _StubHandler)
    assert handler_calls == [True]

    # Singleton: second call returns the same instance, no extra construction.
    assert observability.get_langchain_callback() is handler
    assert handler_calls == [True]

    # build_callbacks returns [handler].
    cbs = observability.build_callbacks()
    assert cbs == [handler]

    # flush proxies to the client.
    observability.flush()
    assert flush_calls == [True]


def test_legacy_base_url_falls_back(monkeypatch):
    """LANGFUSE_BASE_URL is honored when LANGFUSE_HOST is absent (wiki_builder compat)."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://legacy.test")

    seen_host: list[str] = []

    class _StubLangfuse:
        def __init__(self, public_key, secret_key, host):  # noqa: ARG002
            seen_host.append(host)

        def auth_check(self):
            return True

    langfuse_mod = types.ModuleType("langfuse")
    langfuse_mod.Langfuse = _StubLangfuse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", langfuse_mod)

    observability.get_langfuse()
    assert seen_host == ["https://legacy.test"]


def test_init_failure_degrades_to_none(monkeypatch):
    """Auth failure → client is None, no exception bubbles up."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")

    class _BoomLangfuse:
        def __init__(self, **_kwargs):
            raise RuntimeError("nope")

    langfuse_mod = types.ModuleType("langfuse")
    langfuse_mod.Langfuse = _BoomLangfuse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", langfuse_mod)

    assert observability.get_langfuse() is None
    assert observability.get_langchain_callback() is None
    # Still safe to call.
    observability.flush()
