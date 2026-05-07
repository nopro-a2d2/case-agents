"""alias_resolver 의 그룹 정규화·흡수 로직 단위 테스트.

LLM 호출 부분은 테스트하지 않고, _normalize_groups 와 absorb_group 만 검증.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wiki_builder.alias_resolver import _normalize_groups, absorb_group
from wiki_builder.config import wiki_settings
from wiki_builder.models import Registry
from wiki_builder.wiki_store import append_managed_raw_subsection, write_entity_page


@pytest.fixture
def case_dir(tmp_path: Path) -> Path:
    """임시 case 디렉토리 + apply_case_path 효과 모사."""
    case = tmp_path / "case-x"
    (case / "wiki-output" / "entities").mkdir(parents=True)
    (case / "wiki-output" / "concepts").mkdir(parents=True)
    (case / "cache").mkdir(parents=True)
    wiki_settings.WIKI_OUTPUT_DIR = case / "wiki-output"
    wiki_settings.CACHE_DIR = case / "cache"
    yield case


def _registered_page(reg: Registry, name: str, type_: str, source_id: str, body: str) -> str:
    """registry 에 entry 등록 + sentinel-managed 본문 파일 생성. entry id 반환."""
    entry = reg.register(name_ko=name, type=type_, source_id=source_id, pages=[1])
    append_managed_raw_subsection(
        entry,
        source_id,
        body,
        is_concept=(type_ == "topic"),
    )
    return entry.id


def test_normalize_groups_keeps_valid_and_fills_missing() -> None:
    raw = [["entity-001", "entity-002"], ["entity-003"]]
    valid = {"entity-001", "entity-002", "entity-003", "entity-004"}
    out = _normalize_groups(raw, valid)
    flat = sorted(eid for g in out for eid in g)
    assert flat == ["entity-001", "entity-002", "entity-003", "entity-004"]
    # entity-004 가 1-element 그룹으로 보충되었는가
    assert any(g == ["entity-004"] for g in out)


def test_normalize_groups_drops_unknown_ids() -> None:
    raw = [["entity-001", "entity-XXX"]]
    valid = {"entity-001"}
    out = _normalize_groups(raw, valid)
    assert out == [["entity-001"]]


def test_normalize_groups_dedup_within_groups() -> None:
    raw = [["entity-001", "entity-001"], ["entity-001"]]
    valid = {"entity-001"}
    out = _normalize_groups(raw, valid)
    flat = [eid for g in out for eid in g]
    assert flat.count("entity-001") == 1


def test_normalize_groups_handles_garbage() -> None:
    raw = "not a list"
    valid = {"entity-001"}
    out = _normalize_groups(raw, valid)
    assert sorted(g[0] for g in out) == ["entity-001"]


def test_absorb_group_picks_max_source_count_as_canonical(case_dir: Path) -> None:
    reg = Registry(prefix="entity")
    canonical_id = _registered_page(reg, "윤경림", "person", "100", "- 사실 A (source-100:1)")
    absorbed_id = _registered_page(reg, "윤 사장", "person", "200", "- 사실 B (source-200:1)")
    # canonical 에 source 더 추가해 더 많게
    reg.add_source(canonical_id, "101", pages=[2])
    reg.add_source(canonical_id, "102", pages=[3])

    chosen, absorbed = absorb_group(
        reg, [canonical_id, absorbed_id], write_entity_page
    )

    assert chosen == canonical_id
    assert absorbed == [absorbed_id]
    # alias 등록
    assert "윤 사장" in reg.entries[canonical_id].aliases
    # source union
    assert "200" in reg.entries[canonical_id].source_ids
    # name_index 갱신
    assert reg.name_index["윤 사장"] == canonical_id
    # 흡수 entry 삭제
    assert absorbed_id not in reg.entries
    # 흡수 페이지 파일 삭제
    assert not (wiki_settings.WIKI_OUTPUT_DIR / "entities" / f"{absorbed_id}.md").exists()
    # canonical 페이지의 RAW 에 흡수 source-200 서브섹션 병합
    canonical_body = (
        wiki_settings.WIKI_OUTPUT_DIR / reg.entries[canonical_id].file
    ).read_text(encoding="utf-8")
    assert "### source-100" in canonical_body
    assert "### source-200" in canonical_body
    assert "사실 B" in canonical_body


def test_absorb_group_singleton_noop(case_dir: Path) -> None:
    reg = Registry(prefix="entity")
    only = _registered_page(reg, "혼자", "person", "1", "본문")

    chosen, absorbed = absorb_group(reg, [only], lambda e, b: None)
    assert chosen == only
    assert absorbed == []
    assert only in reg.entries


def test_absorb_group_preserves_pages(case_dir: Path) -> None:
    reg = Registry(prefix="entity")
    # _registered_page 가 page=[1] 으로 초기 등록하므로 추가 페이지는 union 됨
    canonical_id = _registered_page(reg, "KT", "org", "100", "본문")
    absorbed_id = _registered_page(reg, "주식회사 KT", "org", "200", "본문 B")
    reg.add_source(canonical_id, "100", pages=[2])
    reg.add_source(absorbed_id, "200", pages=[3, 4])

    absorb_group(reg, [canonical_id, absorbed_id], lambda e, b: None)

    pmap = reg.entries[canonical_id].source_page_map
    assert sorted(pmap["100"]) == [1, 2]
    # 흡수된 200 의 초기 [1] 도 함께 union 됨
    assert sorted(pmap["200"]) == [1, 3, 4]
