"""Phase 2: 엔티티 점진적 성장 (LLM 호출 0회, append-only RAW 누적).

각 문서의 entity 출현 정보(_extract_entity_info)를 RAW 섹션에 ``### source-N``
서브섹션으로 append 한다. 합성(prose 요약)은 별도 phase ``synth`` 에서
``synthesizer.run_synthesis`` 가 entity 단위로 1회씩 LLM 호출.
"""

import asyncio
import logging

from wiki_builder.models import CompileResult, ExtractedEntity, Registry
from wiki_builder.wiki_store import append_managed_raw_subsection, load_registry, save_registry

logger = logging.getLogger(__name__)


def _citation(doc_id: str, pages: list[int]) -> str:
    return f" (source-{doc_id})"


def _extract_entity_info(
    result: CompileResult, entity: ExtractedEntity
) -> tuple[str, list[int]]:
    """source 컴파일 결과에서 특정 엔티티 관련 정보 추출."""
    doc_id = result.doc_id
    parts: list[str] = []
    all_pages: set[int] = set()

    for p in result.key_facts.persons:
        if entity.name_ko in p.name:
            parts.append(f"- 인물: {p.name} — {p.role}{_citation(doc_id, p.pages)}")
            all_pages.update(p.pages)

    for o in result.key_facts.organizations:
        if entity.name_ko in o.name:
            parts.append(f"- 조직: {o.name} — {o.role}{_citation(doc_id, o.pages)}")
            all_pages.update(o.pages)

    for d in result.key_facts.dates:
        if entity.name_ko in d.event:
            parts.append(f"- 날짜: {d.date} — {d.event}{_citation(doc_id, d.pages)}")
            all_pages.update(d.pages)

    for a in result.key_facts.amounts:
        if entity.name_ko in a.context:
            parts.append(f"- 금액: {a.amount} — {a.context}{_citation(doc_id, a.pages)}")
            all_pages.update(a.pages)

    for s in result.detailed_content:
        if entity.name_ko in s.text:
            parts.append(f"- {s.text.strip()}{_citation(doc_id, s.pages)}")
            all_pages.update(s.pages)

    if not parts:
        parts.append(f"- {entity.name_ko}이(가) 문서에서 언급됨{_citation(doc_id, [])}")
        parts.append(f"- 문서 요약: {result.summary[:300]}")

    return "\n".join(parts), sorted(all_pages)


async def process_one_document(
    doc_id: str,
    result: CompileResult,
    registry: Registry,
    registry_lock: asyncio.Lock,
    entity_locks: dict[str, asyncio.Lock],
) -> int:
    """문서의 entity 출현을 등록 + RAW 서브섹션 append. LLM 호출 없음."""
    if not result.entities:
        return 0

    target_map: dict[str, str] = {}
    info_cache: dict[str, str] = {}

    async with registry_lock:
        for entity in result.entities:
            info, pages = _extract_entity_info(result, entity)
            info_cache[entity.name_ko] = info
            existing = registry.find_by_name(entity.name_ko)
            if existing:
                registry.add_source(existing.id, doc_id, pages=pages)
                target_map[entity.name_ko] = existing.id
            else:
                entry = registry.register(
                    name_ko=entity.name_ko,
                    type=entity.type,
                    source_id=doc_id,
                    pages=pages,
                )
                target_map[entity.name_ko] = entry.id

    for entity in result.entities:
        target_id = target_map[entity.name_ko]
        lock = entity_locks.setdefault(target_id, asyncio.Lock())
        async with lock:
            entry = registry.entries[target_id]
            await asyncio.to_thread(
                append_managed_raw_subsection,
                entry,
                doc_id,
                info_cache[entity.name_ko],
                is_concept=False,
            )

    return len(result.entities)


async def run_phase2(
    compile_results: dict[str, CompileResult],
    doc_order: list[str],
    concurrency: int = 10,
) -> Registry:
    """Phase 2: 엔티티 점진적 성장 (문서 간 병렬, LLM 호출 0회)"""
    registry = load_registry("entity", prefix="entity")

    registry_lock = asyncio.Lock()
    entity_locks: dict[str, asyncio.Lock] = {}
    sem = asyncio.Semaphore(concurrency)

    processed_ids: set[str] = set()
    for entry in registry.entries.values():
        processed_ids.update(entry.source_ids)

    remaining = [
        did for did in doc_order if did in compile_results and did not in processed_ids
    ]
    logger.info(
        "Phase 2: 총 %d개 문서, 이미 처리 %d개, 남은 %d개, 동시성 %d",
        len(doc_order),
        len(processed_ids),
        len(remaining),
        concurrency,
    )

    progress = {"done": 0, "entities": 0, "failed": 0}

    async def process_with_sem(doc_id: str) -> None:
        async with sem:
            try:
                result = compile_results[doc_id]
                count = await process_one_document(
                    doc_id, result, registry, registry_lock, entity_locks
                )
                progress["done"] += 1
                progress["entities"] += count
            except Exception:
                progress["done"] += 1
                progress["failed"] += 1
                logger.warning("문서 처리 실패: doc_id=%s", doc_id, exc_info=True)

            if progress["done"] % 50 == 0:
                async with registry_lock:
                    save_registry(registry, "entity")
                logger.info(
                    "Phase 2 진행: %d/%d 문서, 엔티티 %d개 (레지스트리 %d개, 실패 %d)",
                    progress["done"],
                    len(remaining),
                    progress["entities"],
                    len(registry.entries),
                    progress["failed"],
                )

    await asyncio.gather(*[process_with_sem(doc_id) for doc_id in remaining])
    save_registry(registry, "entity")
    logger.info(
        "Phase 2 완료: %d개 문서, 엔티티 %d개 처리, 레지스트리 %d개, 실패 %d",
        progress["done"],
        progress["entities"],
        len(registry.entries),
        progress["failed"],
    )
    return registry
