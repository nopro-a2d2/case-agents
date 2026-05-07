"""Unit tests for the session-scoped write_todos tool."""

from __future__ import annotations

import asyncio
import json

import pytest

from case_agent.tools.todos import TodoStore, build_write_todos_tool


def _invoke(tool, payload):
    return asyncio.run(tool.ainvoke(payload))


def test_replace_all_overwrites_store():
    store = TodoStore()
    tool = build_write_todos_tool(store)

    out = _invoke(tool, {"todos": [
        {"content": "공소장 정독", "status": "in_progress"},
        {"content": "쟁점별 증거 정리", "status": "pending"},
    ]})
    assert json.loads(out) == {"ok": True, "count": 2}
    assert store.snapshot() == [
        {"content": "공소장 정독", "status": "in_progress"},
        {"content": "쟁점별 증거 정리", "status": "pending"},
    ]

    # second call replaces — does not append
    _invoke(tool, {"todos": [
        {"content": "공소장 정독", "status": "completed"},
    ]})
    assert store.snapshot() == [
        {"content": "공소장 정독", "status": "completed"},
    ]


def test_empty_list_clears_store():
    store = TodoStore()
    tool = build_write_todos_tool(store)
    _invoke(tool, {"todos": [{"content": "x", "status": "pending"}]})
    out = _invoke(tool, {"todos": []})
    assert json.loads(out) == {"ok": True, "count": 0}
    assert store.snapshot() == []


def test_invalid_status_rejected():
    store = TodoStore()
    tool = build_write_todos_tool(store)
    with pytest.raises(Exception):
        _invoke(tool, {"todos": [{"content": "x", "status": "bogus"}]})
    # store stays empty on validation error
    assert store.snapshot() == []


def test_blank_content_rejected():
    store = TodoStore()
    tool = build_write_todos_tool(store)
    with pytest.raises(Exception):
        _invoke(tool, {"todos": [{"content": "", "status": "pending"}]})


def test_snapshot_is_independent_copy():
    """snapshot() must not return the live list — caller mutations
    shouldn't leak into the store."""
    store = TodoStore()
    tool = build_write_todos_tool(store)
    _invoke(tool, {"todos": [{"content": "a", "status": "pending"}]})
    snap = store.snapshot()
    snap.append({"content": "b", "status": "pending"})
    assert len(store.snapshot()) == 1
