"""Tests for read_with_anchor (line/page/section) and list_evidence."""

from __future__ import annotations

import pytest

from case_agent.tools.citation import (
    Citation,
    list_evidence,
    parse_citation,
    read_with_anchor,
)
from case_agent.workspace import LocalFS


CASE_ID = "spark"


def _ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


def test_parse_citation_basic() -> None:
    c = parse_citation("json/1.json#p2")
    assert c.path == "json/1.json"
    assert c.anchor == "p2"
    assert str(c) == "json/1.json#p2"


def test_read_with_anchor_page() -> None:
    ws = _ws()
    r = read_with_anchor(ws, "json/1.json#p1")
    assert r.kind == "page"
    assert "고발장" in r.snippet
    assert r.citation == "json/1.json#p1"


def test_read_with_anchor_lines() -> None:
    ws = _ws()
    r = read_with_anchor(ws, "wiki-output/overview.md#L1-L5")
    assert r.kind == "lines"
    assert r.snippet
    # at most 5 lines
    assert r.snippet.count("\n") <= 4


def test_read_with_anchor_section() -> None:
    ws = _ws()
    r = read_with_anchor(ws, "wiki-output/sources/source-1.md#sec:요약")
    assert r.kind == "section"
    assert "고발" in r.snippet


def test_read_with_anchor_bad_anchor_raises() -> None:
    ws = _ws()
    with pytest.raises(ValueError):
        read_with_anchor(ws, "json/1.json#p99999")


def test_read_with_anchor_page_range() -> None:
    ws = _ws()
    r = read_with_anchor(ws, "json/1.json#p1..2")
    assert r.kind == "page"
    assert "--- p1 ---" in r.snippet
    assert "--- p2 ---" in r.snippet
    assert r.citation == "json/1.json#p1..2"


def test_read_with_anchor_page_range_single_normalized() -> None:
    ws = _ws()
    r = read_with_anchor(ws, "json/1.json#p1..1")
    assert r.kind == "page"
    # canonical citation collapses pA..A → pA
    assert r.citation == "json/1.json#p1"


def test_read_with_anchor_legacy_dash_range_rejected() -> None:
    """`p1-5` is not the supported grammar — must raise with a hint."""
    ws = _ws()
    with pytest.raises(ValueError) as excinfo:
        read_with_anchor(ws, "json/1.json#p1-5")
    assert "pA..B" in str(excinfo.value)


def test_read_with_anchor_page_range_not_found() -> None:
    ws = _ws()
    with pytest.raises(ValueError):
        read_with_anchor(ws, "json/1.json#p9000..9001")


def test_list_evidence_smoke() -> None:
    ws = _ws()
    items = list_evidence(ws, limit=5)
    assert items
    assert all(it.json_path.startswith("json/") for it in items)
    assert all(it.source_id for it in items)


def test_list_evidence_filter_by_name() -> None:
    ws = _ws()
    items = list_evidence(ws, name_contains="고발장", limit=10)
    assert any("고발장" in it.title for it in items)
