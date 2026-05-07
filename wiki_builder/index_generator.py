"""Phase 5: index.md, overview.md 생성"""

import logging
from collections import defaultdict

from wiki_builder.config import wiki_settings
from wiki_builder.llm import get_genai_client
from wiki_builder.models import Registry
from wiki_builder.observability import log_generation
from wiki_builder.prompts import OVERVIEW_PROMPT
from wiki_builder.wiki_store import load_registry, wiki_dir

logger = logging.getLogger(__name__)


def _generate_index_md(
    entity_registry: Registry,
    concept_registry: Registry,
    source_pages: list[dict],
) -> str:
    """index.md 내용 생성"""
    case_label = wiki_settings.WIKI_OUTPUT_DIR.parent.name
    lines = [f"# {case_label} 사건 위키 인덱스", ""]

    # 인물
    persons = [e for e in entity_registry.entries.values() if e.type == "person"]
    persons.sort(key=lambda e: len(e.source_ids), reverse=True)
    if persons:
        lines.append(f"## 인물 ({len(persons)}명)")
        for e in persons:
            lines.append(f"- [{e.name_ko}]({e.file}) — {e.type} ({len(e.source_ids)}개 문서)")
        lines.append("")

    # 조직
    orgs = [e for e in entity_registry.entries.values() if e.type == "org"]
    orgs.sort(key=lambda e: len(e.source_ids), reverse=True)
    if orgs:
        lines.append(f"## 조직 ({len(orgs)}개)")
        for e in orgs:
            lines.append(f"- [{e.name_ko}]({e.file}) — ({len(e.source_ids)}개 문서)")
        lines.append("")

    # 기타 엔티티
    others = [e for e in entity_registry.entries.values() if e.type not in ("person", "org")]
    if others:
        others.sort(key=lambda e: len(e.source_ids), reverse=True)
        lines.append(f"## 기타 엔티티 ({len(others)}개)")
        for e in others:
            lines.append(f"- [{e.name_ko}]({e.file}) — {e.type} ({len(e.source_ids)}개 문서)")
        lines.append("")

    # 개념
    concepts = sorted(
        concept_registry.entries.values(),
        key=lambda e: len(e.source_ids),
        reverse=True,
    )
    if concepts:
        lines.append(f"## 개념 ({len(concepts)}개)")
        for c in concepts:
            lines.append(f"- [{c.name_ko}]({c.file}) — ({len(c.source_ids)}개 문서)")
        lines.append("")

    # 소스 문서 (카테고리별)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for sp in source_pages:
        by_category[sp.get("category", "기타")].append(sp)

    lines.append(f"## 소스 문서 ({len(source_pages)}개)")
    cat_order = ["공소장", "수사보고서", "진술", "참조법문서", "기타"]
    for cat in cat_order:
        pages = by_category.get(cat, [])
        if not pages:
            continue
        lines.append(f"### {cat} ({len(pages)}개)")
        for sp in pages[:50]:  # 카테고리당 최대 50개 표시
            doc_id = sp.get("id", "")
            title = sp.get("title", "")
            lines.append(f"- [{title}](sources/source-{doc_id}.md)")
        if len(pages) > 50:
            lines.append(f"- ... 외 {len(pages) - 50}개")
        lines.append("")

    # 키워드 인덱스 (상위 엔티티/개념만)
    lines.append("## 키워드 인덱스")
    lines.append("| 키워드 | 관련 페이지 |")
    lines.append("|--------|------------|")
    top_entries = sorted(
        list(entity_registry.entries.values()) + list(concept_registry.entries.values()),
        key=lambda e: len(e.source_ids),
        reverse=True,
    )[:30]
    for e in top_entries:
        source_refs = ", ".join(f"source-{sid}" for sid in e.source_ids[:5])
        if len(e.source_ids) > 5:
            source_refs += f" 외 {len(e.source_ids) - 5}개"
        lines.append(f"| {e.name_ko} | {e.id}, {source_refs} |")

    return "\n".join(lines)


async def _generate_overview(
    source_pages: list[dict],
) -> str:
    """overview.md: 계층적 요약 생성"""
    client = get_genai_client()
    model = wiki_settings.REALTIME_MODEL

    # 카테고리별 요약 수집
    by_category: dict[str, list[str]] = defaultdict(list)
    for sp in source_pages:
        cat = sp.get("category", "기타")
        summary = sp.get("summary", "")
        if summary:
            by_category[cat].append(summary)

    # 카테고리별 요약 생성
    cat_summaries = []
    for cat in ["공소장", "수사보고서", "진술", "참조법문서", "기타"]:
        summaries = by_category.get(cat, [])
        if not summaries:
            continue
        combined = "\n".join(f"- {s[:200]}" for s in summaries[:30])
        cat_summaries.append(f"### {cat} ({len(summaries)}개 문서)\n{combined}")

    category_summaries_text = "\n\n".join(cat_summaries)

    prompt = OVERVIEW_PROMPT.format(category_summaries=category_summaries_text)
    response = client.models.generate_content(
        model=model,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config={"temperature": 0.3},
    )
    overview = response.text or "개요 생성 실패"
    log_generation("overview-generate", model, "categories", overview[:200])
    return overview


async def run_phase5(source_pages: list[dict]) -> None:
    """Phase 5: index.md + overview.md 생성"""
    entity_registry = load_registry("entity", prefix="entity")
    concept_registry = load_registry("concept", prefix="concept")

    # index.md
    index_content = _generate_index_md(entity_registry, concept_registry, source_pages)
    index_path = wiki_dir() / "index.md"
    index_path.write_text(index_content, encoding="utf-8")
    logger.info("index.md 생성: %d줄", len(index_content.splitlines()))

    # overview.md
    overview_body = await _generate_overview(source_pages)
    case_label = wiki_settings.WIKI_OUTPUT_DIR.parent.name
    overview_content = f"# {case_label} 사건 전체 개요\n\n{overview_body}"
    overview_path = wiki_dir() / "overview.md"
    overview_path.write_text(overview_content, encoding="utf-8")
    logger.info("overview.md 생성 완료")
