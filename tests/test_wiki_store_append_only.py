"""wiki_store append-only RAW + SYNTHESIS sentinel 의 멱등성·결정성 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from wiki_builder.config import wiki_settings
from wiki_builder.models import Registry
from wiki_builder.wiki_store import (
    RAW_BLOCK_END,
    RAW_BLOCK_START,
    SYNTHESIS_BLOCK_END,
    SYNTHESIS_BLOCK_START,
    _extract_raw,
    _extract_synth,
    append_managed_raw_subsection,
    merge_raw_subsections_from_body,
    set_managed_synthesis,
    write_entity_page,
)


@pytest.fixture
def case_dir(tmp_path: Path) -> Path:
    case = tmp_path / "case-x"
    (case / "wiki-output" / "entities").mkdir(parents=True)
    (case / "wiki-output" / "concepts").mkdir(parents=True)
    (case / "cache").mkdir(parents=True)
    wiki_settings.WIKI_OUTPUT_DIR = case / "wiki-output"
    wiki_settings.CACHE_DIR = case / "cache"
    yield case


def _new_entity(name: str = "윤경림") -> Registry:
    reg = Registry(prefix="entity")
    reg.register(name_ko=name, type="person", source_id="100", pages=[1])
    return reg


def test_first_append_creates_sentinels(case_dir: Path) -> None:
    reg = _new_entity()
    entry = next(iter(reg.entries.values()))
    append_managed_raw_subsection(entry, "100", "- 인물: 윤경림 — 사장 (source-100:1)")

    body = (wiki_settings.WIKI_OUTPUT_DIR / entry.file).read_text(encoding="utf-8")
    assert RAW_BLOCK_START in body
    assert RAW_BLOCK_END in body
    assert SYNTHESIS_BLOCK_START in body
    assert SYNTHESIS_BLOCK_END in body
    assert "### source-100" in body
    assert "윤경림" in body


def test_idempotent_same_source_id(case_dir: Path) -> None:
    reg = _new_entity()
    entry = next(iter(reg.entries.values()))
    append_managed_raw_subsection(entry, "100", "- 사실 A (source-100:1)")
    append_managed_raw_subsection(entry, "100", "- 사실 A (source-100:1)")

    body = (wiki_settings.WIKI_OUTPUT_DIR / entry.file).read_text(encoding="utf-8")
    assert body.count("### source-100") == 1


def test_appends_distinct_sources(case_dir: Path) -> None:
    reg = _new_entity()
    entry = next(iter(reg.entries.values()))
    append_managed_raw_subsection(entry, "100", "- A")
    append_managed_raw_subsection(entry, "200", "- B")

    body = (wiki_settings.WIKI_OUTPUT_DIR / entry.file).read_text(encoding="utf-8")
    assert body.count("### source-") == 2
    assert "### source-100" in body
    assert "### source-200" in body


def test_synthesis_does_not_clobber_raw(case_dir: Path) -> None:
    reg = _new_entity()
    entry = next(iter(reg.entries.values()))
    append_managed_raw_subsection(entry, "100", "- 사실 A (source-100:1)")

    set_managed_synthesis(entry, "윤경림은 KT 사장이다.")

    body = (wiki_settings.WIKI_OUTPUT_DIR / entry.file).read_text(encoding="utf-8")
    assert "사실 A" in body
    assert "윤경림은 KT 사장이다." in body
    assert "### source-100" in body


def test_extract_helpers_round_trip(case_dir: Path) -> None:
    reg = _new_entity()
    entry = next(iter(reg.entries.values()))
    append_managed_raw_subsection(entry, "100", "- A (source-100:1)")
    set_managed_synthesis(entry, "합성 본문")

    body = (wiki_settings.WIKI_OUTPUT_DIR / entry.file).read_text(encoding="utf-8")
    raw = _extract_raw(body)
    synth = _extract_synth(body)
    assert "### source-100" in raw
    assert "A (source-100:1)" in raw
    assert "합성 본문" in synth


def test_merge_raw_subsections_idempotent(case_dir: Path) -> None:
    reg = _new_entity("KT")
    canonical = next(iter(reg.entries.values()))
    # absorbed entry 페이지 시뮬레이션
    absorbed_body = (
        f"# 주식회사 KT\n\n"
        f"{RAW_BLOCK_START}\n"
        f"## 출처별 사실\n\n"
        f"### source-200\n- 조직: KT — 피해자 (source-200:1)\n"
        f"\n### source-300\n- 조직: KT (source-300:2)\n"
        f"{RAW_BLOCK_END}\n"
    )
    merge_raw_subsections_from_body(canonical, absorbed_body)
    merge_raw_subsections_from_body(canonical, absorbed_body)  # 중복 호출 — idempotent

    body = (wiki_settings.WIKI_OUTPUT_DIR / canonical.file).read_text(encoding="utf-8")
    assert body.count("### source-200") == 1
    assert body.count("### source-300") == 1


def test_write_entity_page_preserves_managed_sections(case_dir: Path) -> None:
    """[backward-compat] write_entity_page(entry, body) 의 body 인자는 무시되고
    기존 RAW/SYNTHESIS 가 보존되어야 한다."""
    reg = _new_entity()
    entry = next(iter(reg.entries.values()))
    append_managed_raw_subsection(entry, "100", "- 사실 A (source-100:1)")
    set_managed_synthesis(entry, "합성")

    write_entity_page(entry, body="이건 무시됨")

    body = (wiki_settings.WIKI_OUTPUT_DIR / entry.file).read_text(encoding="utf-8")
    assert "사실 A" in body
    assert "합성" in body
    assert "이건 무시됨" not in body


def test_sources_block_reflects_registry(case_dir: Path) -> None:
    reg = _new_entity()
    entry = next(iter(reg.entries.values()))
    reg.add_source(entry.id, "200", pages=[3, 4])
    append_managed_raw_subsection(entry, "100", "- A")

    body = (wiki_settings.WIKI_OUTPUT_DIR / entry.file).read_text(encoding="utf-8")
    # SOURCES 블록에 두 source 모두 표시
    assert "source-100" in body
    assert "source-200" in body
