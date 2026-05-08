"""Unit tests for case_agent.loop.labels.build_label_fn."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from case_agent.loop.labels import build_label_fn
from case_agent.workspace import LocalFS


@pytest.fixture
def ws(tmp_path: Path) -> LocalFS:
    case = tmp_path / "case-X"
    (case / "cache").mkdir(parents=True)
    (case / "json").mkdir()

    (case / "cache" / "entity_registry.json").write_text(
        json.dumps(
            {
                "entries": {
                    "entity-310": {"id": "entity-310", "name_ko": "윤경림", "type": "person"},
                }
            },
            ensure_ascii=False,
        )
    )
    (case / "cache" / "concept_registry.json").write_text(
        json.dumps(
            {
                "entries": {
                    "concept-002": {"id": "concept-002", "name_ko": "업무상 배임", "type": "topic"},
                }
            },
            ensure_ascii=False,
        )
    )

    (case / "json" / "석명준비명령.json").write_text(
        json.dumps(
            {"id": "cdoc_AAA19", "number": "석명준비명령", "name": "석명준비명령"},
            ensure_ascii=False,
        )
    )
    (case / "json" / "갑3-3.json").write_text(
        json.dumps(
            {
                "id": "cdoc_BBB",
                "number": "갑 제3-3호증",
                "name": "등기사항전부증명서",
            },
            ensure_ascii=False,
        )
    )
    return LocalFS(case_id="case-X", root=str(tmp_path))


def test_smart_search_label(ws: LocalFS) -> None:
    label = build_label_fn(ws)("smart_search", {"query": "피고인 인적사항"})
    assert label == {"action": "자료 검색", "subject": "피고인 인적사항"}


def test_read_with_anchor_entity(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "wiki-output/entities/entity-310.md"},
    )
    assert label == {"action": "문서 검토", "subject": "윤경림 엔티티 확인"}


def test_read_with_anchor_concept_with_section_anchor(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "wiki-output/concepts/concept-002.md#sec:1-개념-정의"},
    )
    assert label == {"action": "문서 검토", "subject": "업무상 배임 개념 확인 (§1-개념-정의)"}


def test_read_with_anchor_concept_no_anchor(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "wiki-output/concepts/concept-002.md"},
    )
    assert label == {"action": "문서 검토", "subject": "업무상 배임 개념 확인"}


def test_read_with_anchor_source_uses_name_only_when_number_matches(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "wiki-output/sources/source-cdoc_AAA19.md"},
    )
    assert label == {"action": "문서 검토", "subject": "석명준비명령"}


def test_read_with_anchor_source_combines_number_and_name(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "wiki-output/sources/source-cdoc_BBB.md"},
    )
    assert label == {"action": "문서 검토", "subject": "갑 제3-3호증 : 등기사항전부증명서"}


def test_read_with_anchor_json_path_resolves_via_filename_stem(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "json/갑3-3.json#p1"},
    )
    assert label == {
        "action": "문서 검토",
        "subject": "갑 제3-3호증 : 등기사항전부증명서 (1쪽)",
    }


def test_read_with_anchor_json_page_range(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "json/갑3-3.json#p1..5"},
    )
    assert label == {
        "action": "문서 검토",
        "subject": "갑 제3-3호증 : 등기사항전부증명서 (1-5쪽)",
    }


def test_read_with_anchor_line_anchor(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "txt/something.txt#L120-L145"},
    )
    assert label == {"action": "문서 검토", "subject": "txt/something.txt (L120-L145)"}


def test_unknown_path_falls_back_to_path(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "txt/something.txt#L1-L5"},
    )
    assert label == {"action": "문서 검토", "subject": "txt/something.txt (L1-L5)"}


def test_list_evidence_empty_filters(ws: LocalFS) -> None:
    label = build_label_fn(ws)("list_evidence", {})
    assert label == {"action": "증거 목록", "subject": "전체"}


def test_list_evidence_with_filters(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "list_evidence",
        {"person": "피고인", "category": "수사기록"},
    )
    assert label == {"action": "증거 목록", "subject": "인물: 피고인, 분류: 수사기록"}


def test_verify_citations_label(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "verify_citations",
        {"path": "artifacts/timeline_v1.md"},
    )
    assert label == {"action": "인용 검증", "subject": "artifacts/timeline_v1.md"}


def test_check_completeness_translates_kind(ws: LocalFS) -> None:
    label = build_label_fn(ws)(
        "check_completeness",
        {"kind": "evidence_acknowledgment", "path": "drafts/x.md"},
    )
    assert label == {"action": "구조 점검", "subject": "증거인부서"}


def test_unknown_tool_returns_none(ws: LocalFS) -> None:
    assert build_label_fn(ws)("write_todos", {"todos": []}) is None
    assert build_label_fn(ws)("calculate", {"code": "1+1"}) is None


def test_empty_query_returns_none(ws: LocalFS) -> None:
    assert build_label_fn(ws)("smart_search", {"query": ""}) is None


def test_missing_registry_files_does_not_crash(tmp_path: Path) -> None:
    case = tmp_path / "empty-case"
    case.mkdir()
    ws = LocalFS(case_id="empty-case", root=str(tmp_path))
    label = build_label_fn(ws)(
        "read_with_anchor",
        {"citation": "wiki-output/entities/entity-001.md"},
    )
    # Falls back to bare id when registry is unreadable.
    assert label == {"action": "문서 검토", "subject": "entity-001"}
