"""Shared Langfuse observability for case_agent and wiki_builder.

The Langfuse + LangChain integration is just a callback handler — when passed
into ``RunnableConfig``, LangChain auto-emits spans for every model and tool
invocation, and recursive ``query()`` calls inherit the same trace.

This module is env-driven and fail-soft:
  * ``LANGFUSE_ENABLED=false`` (default) → every getter returns ``None`` and
    ``langfuse`` is never imported, so the dep stays optional.
  * ``LANGFUSE_HOST`` follows the upstream doc; legacy ``LANGFUSE_BASE_URL``
    (used by ``wiki_builder``) is honored as a fallback.
  * Any import / auth failure logs a warning and degrades to ``None`` so a
    misconfigured Langfuse can never crash the agent.

Public API:
  * :func:`get_langfuse` — process-wide ``Langfuse`` client singleton.
  * :func:`get_langchain_callback` — process-wide ``CallbackHandler`` singleton.
  * :func:`build_callbacks` — convenience: ``[handler]`` or ``None``.
  * :func:`flush` — best-effort flush; safe to call when disabled.
  * :func:`reset_for_test` — drop singletons so tests can re-init with new env.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from ._env import load_env

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = logging.getLogger(__name__)

_client: "Langfuse | None" = None
_handler: Any | None = None
_client_initialized = False
_handler_initialized = False


def _enabled() -> bool:
    load_env()
    return os.environ.get("LANGFUSE_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _host() -> str:
    return (
        os.environ.get("LANGFUSE_HOST")
        or os.environ.get("LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    )


def get_langfuse() -> Any | None:
    """Return the shared ``Langfuse`` client, or ``None`` when disabled / failed."""
    global _client, _client_initialized
    if not _enabled():
        return None
    if _client_initialized:
        return _client
    _client_initialized = True
    try:
        from langfuse import Langfuse
    except ImportError:
        logger.warning(
            "langfuse not installed — install the [obs] extra: "
            "uv pip install -e '.[obs]'"
        )
        return None
    try:
        _client = Langfuse(
            public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=_host(),
        )
        _client.auth_check()
        logger.info("Langfuse connected: %s", _host())
    except Exception:  # noqa: BLE001 — never crash the agent on observability failure
        logger.warning("Langfuse init failed — tracing disabled", exc_info=True)
        _client = None
    return _client


def get_langchain_callback() -> Any | None:
    """Return the shared LangChain ``CallbackHandler`` singleton, or ``None``.

    Pass into ``config={"callbacks": [handler]}``; LangChain will propagate it
    through model streams, tool ``ainvoke``, and recursive runnable calls.
    """
    global _handler, _handler_initialized
    if not _enabled():
        return None
    if _handler_initialized:
        return _handler
    _handler_initialized = True
    if get_langfuse() is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        logger.warning(
            "langfuse[langchain] not installed — CallbackHandler unavailable. "
            "Install with: uv pip install -e '.[obs]'"
        )
        return None
    try:
        _handler = CallbackHandler()
    except Exception:  # noqa: BLE001
        logger.warning("Langfuse CallbackHandler init failed", exc_info=True)
        _handler = None
    return _handler


def build_callbacks() -> list | None:
    """Return ``[handler]`` when tracing is on, else ``None``.

    Callers thread this into ``config={"callbacks": cbs}`` only when the list
    is truthy, so disabled mode adds zero kwargs to LangChain calls.
    """
    handler = get_langchain_callback()
    return [handler] if handler is not None else None


def flush() -> None:
    """Best-effort flush of buffered spans. Safe to call when disabled."""
    client = _client if _client_initialized else None
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # noqa: BLE001
        logger.debug("Langfuse flush failed", exc_info=True)


def reset_for_test() -> None:
    """Clear singletons. Tests use this between fixtures with mutated env."""
    global _client, _handler, _client_initialized, _handler_initialized
    _client = None
    _handler = None
    _client_initialized = False
    _handler_initialized = False


__all__ = [
    "build_callbacks",
    "flush",
    "get_langchain_callback",
    "get_langfuse",
    "reset_for_test",
]
