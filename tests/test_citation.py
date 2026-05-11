"""Tests for parse_citation, build_id_registry, read_evidence, list_evidence."""

from __future__ import annotations

import pytest

from case_agent.tools.citation import (
    build_id_registry,
    list_evidence,
    parse_citation,
    read_evidence,
    resolve_id,
)
from case_agent.workspace import LocalFS


CASE_ID = "spark"


def _ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


# ---- parse_citation -------------------------------------------------------


def test_parse_citation_basic() -> None:
    c = parse_citation("@@[1]")
    assert c.id == "1"
    assert str(c) == "@@[1]"


def test_parse_citation_ulid_like() -> None:
    c = parse_citation("@@[cdoc_01KKH4TTAG000000000000000S]")
    assert c.id == "cdoc_01KKH4TTAG000000000000000S"


def test_parse_citation_rejects_old_grammar() -> None:
    with pytest.raises(ValueError):
        parse_citation("json/1.json#p2")


def test_parse_citation_rejects_empty() -> None:
    with pytest.raises(ValueError):
        parse_citation("@@[]")


# ---- registry -------------------------------------------------------------


def test_build_id_registry_smoke() -> None:
    ws = _ws()
    reg = build_id_registry(ws)
    assert reg
    assert all(p.startswith("json/") for p in reg.values())
    # spark fixture: id "1" should resolve to json/1.json
    assert reg.get("1") == "json/1.json"


def test_build_id_registry_is_cached() -> None:
    ws = _ws()
    a = build_id_registry(ws)
    b = build_id_registry(ws)
    assert a is b  # same dict instance returned from cache


def test_resolve_id_unknown() -> None:
    ws = _ws()
    with pytest.raises(KeyError):
        resolve_id(ws, "no-such-doc-id")


# ---- read_evidence --------------------------------------------------------


def test_read_evidence_page() -> None:
    ws = _ws()
    r = read_evidence(ws, "1", start_page=1)
    assert r.kind == "page"
    assert r.id == "1"
    assert r.citation == "@@[1]"
    assert "고발장" in r.snippet


def test_read_evidence_page_range() -> None:
    ws = _ws()
    r = read_evidence(ws, "1", start_page=1, end_page=2)
    assert r.kind == "page"
    assert "--- p1 ---" in r.snippet
    assert "--- p2 ---" in r.snippet


def test_read_evidence_full() -> None:
    ws = _ws()
    r = read_evidence(ws, "1")
    assert r.kind == "full"
    assert r.snippet


def test_read_evidence_unknown_id_raises() -> None:
    ws = _ws()
    with pytest.raises(KeyError):
        read_evidence(ws, "no-such-id")


def test_read_evidence_page_not_found() -> None:
    ws = _ws()
    with pytest.raises(ValueError):
        read_evidence(ws, "1", start_page=99999)


def test_read_evidence_rejects_multiple_addressing_modes() -> None:
    ws = _ws()
    with pytest.raises(ValueError):
        read_evidence(ws, "1", start_page=1, start_line=1)


# ---- list_evidence --------------------------------------------------------


def test_list_evidence_smoke() -> None:
    ws = _ws()
    items = list_evidence(ws, limit=5)
    assert items
    assert all(it.json_path.startswith("json/") for it in items)
    assert all(it.id for it in items)


def test_list_evidence_filter_by_name() -> None:
    ws = _ws()
    items = list_evidence(ws, name_contains="고발장", limit=10)
    assert any("고발장" in it.title for it in items)
