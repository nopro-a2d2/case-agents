"""Phase 3: 개념 점진적 성장 (LLM 호출 0회, append-only RAW 누적).

Phase 2 와 동일한 패턴 — concept 출현 정보를 RAW 섹션에 ``### source-N``
서브섹션으로 append. 합성은 phase ``synth`` 에서 1회.
"""

import asyncio
import logging

from wiki_builder.models import CompileResult, ExtractedConcept, Registry
from wiki_builder.wiki_store import append_managed_raw_subsection, load_registry, save_registry

logger = logging.getLogger(__name__)


def _citation(doc_id: str, pages: list[int]) -> str:
    if not pages:
        return f" (source-{doc_id})"
    return f" (source-{doc_id}:" + ",".join(str(p) for p in pages) + ")"


def _extract_concept_info(
    result: CompileResult, concept: ExtractedConcept
) -> tuple[str, list[int]]:
    doc_id = result.doc_id
    parts: list[str] = []
    all_pages: set[int] = set()

    for s in result.detailed_content:
        if concept.name_ko in s.text:
            parts.append(f"- {s.text.strip()}{_citation(doc_id, s.pages)}")
            all_pages.update(s.pages)

    for d in result.key_facts.dates:
        if concept.name_ko in d.event:
            parts.append(f"- 날짜: {d.date} — {d.event}{_citation(doc_id, d.pages)}")
            all_pages.update(d.pages)

    for a in result.key_facts.amounts:
        if concept.name_ko in a.context:
            parts.append(f"- 금액: {a.amount} — {a.context}{_citation(doc_id, a.pages)}")
            all_pages.update(a.pages)

    for lp in result.key_facts.legal_provisions:
        if concept.name_ko in lp:
            parts.append(f"- 법조항: {lp}{_citation(doc_id, [])}")

    if not parts:
        parts.append(f"- 개념: {concept.name_ko} — {concept.description}{_citation(doc_id, [])}")
        parts.append(f"- 문서 요약: {result.summary[:300]}")

    return "\n".join(parts), sorted(all_pages)


async def process_one_document(
    doc_id: str,
    result: CompileResult,
    registry: Registry,
    registry_lock: asyncio.Lock,
    concept_locks: dict[str, asyncio.Lock],
) -> int:
    if not result.concepts:
        return 0

    target_map: dict[str, str] = {}
    info_cache: dict[str, str] = {}

    async with registry_lock:
        for concept in result.concepts:
            info, pages = _extract_concept_info(result, concept)
            info_cache[concept.name_ko] = info
            existing = registry.find_by_name(concept.name_ko)
            if existing:
                registry.add_source(existing.id, doc_id, pages=pages)
                target_map[concept.name_ko] = existing.id
            else:
                entry = registry.register(
                    name_ko=concept.name_ko,
                    type="topic",
                    source_id=doc_id,
                    pages=pages,
                )
                target_map[concept.name_ko] = entry.id

    for concept in result.concepts:
        target_id = target_map[concept.name_ko]
        lock = concept_locks.setdefault(target_id, asyncio.Lock())
        async with lock:
            entry = registry.entries[target_id]
            await asyncio.to_thread(
                append_managed_raw_subsection,
                entry,
                doc_id,
                info_cache[concept.name_ko],
                True,
            )

    return len(result.concepts)


async def run_phase3(
    compile_results: dict[str, CompileResult],
    doc_order: list[str],
    concurrency: int = 10,
) -> Registry:
    """Phase 3: 개념 점진적 성장 (문서 간 병렬, LLM 호출 0회)"""
    registry = load_registry("concept", prefix="concept")

    registry_lock = asyncio.Lock()
    concept_locks: dict[str, asyncio.Lock] = {}
    sem = asyncio.Semaphore(concurrency)

    processed_ids: set[str] = set()
    for entry in registry.entries.values():
        processed_ids.update(entry.source_ids)

    remaining = [
        did for did in doc_order if did in compile_results and did not in processed_ids
    ]
    logger.info(
        "Phase 3: 총 %d개 문서, 이미 처리 %d개, 남은 %d개, 동시성 %d",
        len(doc_order),
        len(processed_ids),
        len(remaining),
        concurrency,
    )

    progress = {"done": 0, "concepts": 0, "failed": 0}

    async def process_with_sem(doc_id: str) -> None:
        async with sem:
            try:
                result = compile_results[doc_id]
                count = await process_one_document(
                    doc_id, result, registry, registry_lock, concept_locks
                )
                progress["done"] += 1
                progress["concepts"] += count
            except Exception:
                progress["done"] += 1
                progress["failed"] += 1
                logger.warning("문서 처리 실패: doc_id=%s", doc_id, exc_info=True)

            if progress["done"] % 50 == 0:
                async with registry_lock:
                    save_registry(registry, "concept")
                logger.info(
                    "Phase 3 진행: %d/%d 문서, 개념 %d개 (레지스트리 %d개, 실패 %d)",
                    progress["done"],
                    len(remaining),
                    progress["concepts"],
                    len(registry.entries),
                    progress["failed"],
                )

    await asyncio.gather(*[process_with_sem(doc_id) for doc_id in remaining])
    save_registry(registry, "concept")
    logger.info(
        "Phase 3 완료: %d개 문서, 개념 %d개 처리, 레지스트리 %d개, 실패 %d",
        progress["done"],
        progress["concepts"],
        len(registry.entries),
        progress["failed"],
    )
    return registry
