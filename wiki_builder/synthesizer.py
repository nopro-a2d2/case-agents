"""Phase 'synth' — entity/concept 페이지의 SYNTHESIS 섹션 LLM 합성.

각 페이지의 RAW 섹션을 읽고 LLM 1회로 prose 합성을 생성, SYNTHESIS 섹션에 기록.
RAW 섹션은 변하지 않으며 (append-only), SYNTHESIS 만 갱신된다.

dirty 추적: 페이지 frontmatter 의 ``synth_source_count`` 와 현재 ``source_count`` 가
같으면 skip. 새 source 가 RAW 에 추가되면 카운트가 어긋나 자동 재합성.
"""

from __future__ import annotations

import asyncio
import logging

import frontmatter

from wiki_builder.config import wiki_settings
from wiki_builder.llm import get_genai_client
from wiki_builder.observability import log_generation
from wiki_builder.prompts import (
    CONCEPT_SYNTHESIS_PROMPT,
    ENTITY_SYNTHESIS_PROMPT,
    ENTITY_SYNTHESIS_SYSTEM,
)
from wiki_builder.wiki_store import (
    _extract_raw,
    load_registry,
    read_page,
    set_managed_synthesis,
    wiki_dir,
)

logger = logging.getLogger(__name__)


def _needs_synthesis(meta: dict) -> bool:
    return int(meta.get("synth_source_count", -1)) != int(meta.get("source_count", 0))


async def _synth_one(
    client,
    model: str,
    entry,
    raw: str,
    is_concept: bool,
) -> str:
    template = CONCEPT_SYNTHESIS_PROMPT if is_concept else ENTITY_SYNTHESIS_PROMPT
    prompt = template.format(name_ko=entry.name_ko, raw=raw[:8000])
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config={"system_instruction": ENTITY_SYNTHESIS_SYSTEM, "temperature": 0.2},
    )
    body = response.text or ""
    in_tok = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
    out_tok = (
        response.usage_metadata.candidates_token_count if response.usage_metadata else 0
    )
    log_generation(
        "concept-synth" if is_concept else "entity-synth",
        model,
        entry.name_ko,
        body[:200],
        input_tokens=in_tok or 0,
        output_tokens=out_tok or 0,
    )
    return body.strip()


async def _run_kind(
    registry_name: str, prefix: str, *, force: bool, concurrency: int
) -> dict:
    """entity 또는 concept 의 모든 entry SYNTHESIS 갱신."""
    registry = load_registry(registry_name, prefix=prefix)
    if not registry.entries:
        logger.info("synth skip: %s registry 비어있음", registry_name)
        return {"total": 0, "synthesized": 0, "skipped": 0}

    is_concept = registry_name == "concept"
    client = get_genai_client()
    model = wiki_settings.REALTIME_MODEL
    sem = asyncio.Semaphore(concurrency)
    progress = {"total": len(registry.entries), "synthesized": 0, "skipped": 0, "failed": 0}

    async def task(entry) -> None:
        async with sem:
            path = wiki_dir() / entry.file
            if not path.exists():
                progress["skipped"] += 1
                return
            try:
                meta, body = read_page(path)
                raw = _extract_raw(body)
                if not raw.strip():
                    progress["skipped"] += 1
                    return
                if not force and not _needs_synthesis(meta):
                    progress["skipped"] += 1
                    return
                synth_body = await _synth_one(client, model, entry, raw, is_concept)
                # SYNTHESIS 갱신 + frontmatter synth_source_count 기록
                set_managed_synthesis(entry, synth_body, is_concept=is_concept)
                _stamp_synth_count(path, len(entry.source_ids))
                progress["synthesized"] += 1
            except Exception:
                progress["failed"] += 1
                logger.warning("synth 실패: %s", entry.id, exc_info=True)

    await asyncio.gather(*[task(e) for e in registry.entries.values()])
    logger.info(
        "synth %s 완료: 합성 %d, skip %d, 실패 %d / 총 %d",
        registry_name,
        progress["synthesized"],
        progress["skipped"],
        progress["failed"],
        progress["total"],
    )
    return progress


def _stamp_synth_count(path, count: int) -> None:
    """frontmatter 에 synth_source_count 기록 — set_managed_synthesis 호출 직후."""
    post = frontmatter.load(str(path))
    post["synth_source_count"] = count
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


async def run_synthesis(force: bool = False, concurrency: int = 8) -> dict:
    """entity + concept 모두 SYNTHESIS 갱신. 통계 dict 반환."""
    e_stats = await _run_kind("entity", prefix="entity", force=force, concurrency=concurrency)
    c_stats = await _run_kind("concept", prefix="concept", force=force, concurrency=concurrency)
    return {
        "entity": e_stats,
        "concept": c_stats,
        "synthesized": e_stats["synthesized"] + c_stats["synthesized"],
    }
