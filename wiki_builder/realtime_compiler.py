"""Phase 1 실시간 컴파일러 (Batch API 대신 실시간 API 사용)

asyncio.Semaphore로 동시 호출 수를 제어하여 병렬 처리합니다.
"""

import asyncio
import logging

from google import genai

from wiki_builder.config import wiki_settings
from wiki_builder.llm import get_genai_client
from wiki_builder.models import CompileResult, CompileResultLLM, Document
from wiki_builder.observability import log_generation
from wiki_builder.compiler import (
    delete_compile_cache,
    load_compile_cache,
    parse_compile_result,
    save_compile_cache,
)
from wiki_builder.prompts import SOURCE_COMPILE_PROMPT, SOURCE_COMPILE_SYSTEM
from wiki_builder.verifier import verify_compile_result

logger = logging.getLogger(__name__)


async def compile_one(
    client: genai.Client,
    doc: Document,
    sem: asyncio.Semaphore,
    progress: dict,
) -> tuple[str, CompileResult | None]:
    """단일 문서 실시간 컴파일"""
    cache_dir = wiki_settings.CACHE_DIR

    # 캐시 확인 — 파싱 실패한 캐시는 즉시 삭제 후 LLM 재호출
    cached = load_compile_cache(cache_dir, doc.id)
    if cached:
        result = parse_compile_result(doc.id, cached)
        if result:
            outcome = verify_compile_result(result, doc)
            result.verification_failures = outcome.failures
            progress["verify_total"] += outcome.total
            progress["verify_failed"] += outcome.failed
            progress["cached"] += 1
            return doc.id, result
        delete_compile_cache(cache_dir, doc.id)

    prompt = SOURCE_COMPILE_PROMPT.format(
        doc_id=doc.id,
        name=doc.name,
        category=doc.category,
        person=doc.person or "없음",
        total_page=doc.total_page,
        token_count=doc.token_count,
        full_text=doc.full_text,
    )

    async with sem:
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=wiki_settings.REALTIME_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config={
                    "system_instruction": SOURCE_COMPILE_SYSTEM,
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                    "response_schema": CompileResultLLM,
                },
            )

            raw_text = response.text or ""
            input_tokens = 0
            output_tokens = 0
            if response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count or 0
                output_tokens = response.usage_metadata.candidates_token_count or 0

            # Langfuse 로깅 (토큰 포함)
            log_generation(
                name="phase1-compile",
                model=wiki_settings.REALTIME_MODEL,
                input_text=f"[doc-{doc.id}] {doc.name}",
                output_text=raw_text[:500],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                trace_name="phase1-source-compile",
            )

            result = parse_compile_result(doc.id, raw_text)
            if result is None:
                # 파싱 실패한 raw_text는 캐시에 남기지 않는다
                # (parse_compile_result가 이미 warning을 출력함)
                progress["failed"] += 1
                return doc.id, None

            # 파싱 성공 시에만 캐시 저장
            save_compile_cache(cache_dir, doc.id, raw_text)

            # Phase 1.5: citation back-check
            outcome = verify_compile_result(result, doc)
            result.verification_failures = outcome.failures
            progress["verify_total"] += outcome.total
            progress["verify_failed"] += outcome.failed

            progress["done"] += 1

            if progress["done"] % 50 == 0:
                total = progress["total"]
                done = progress["done"]
                cached_count = progress["cached"]
                logger.info(
                    "Phase 1 진행: %d/%d (캐시 %d, 실패 %d)",
                    done + cached_count,
                    total,
                    cached_count,
                    progress["failed"],
                )

            return doc.id, result

        except Exception:
            progress["failed"] += 1
            logger.warning("컴파일 실패: doc_id=%s", doc.id, exc_info=True)
            return doc.id, None


async def run_phase1_realtime(
    docs: list[Document],
    concurrency: int = 15,
) -> dict[str, CompileResult]:
    """Phase 1: 실시간 API 병렬 컴파일

    Args:
        docs: 컴파일할 문서 목록
        concurrency: 동시 API 호출 수 (기본 15)

    Returns:
        {doc_id: CompileResult}
    """
    client = get_genai_client()
    sem = asyncio.Semaphore(concurrency)
    progress = {
        "total": len(docs),
        "done": 0,
        "cached": 0,
        "failed": 0,
        "verify_total": 0,
        "verify_failed": 0,
    }

    logger.info("Phase 1 실시간 컴파일 시작: %d개 문서, 동시성 %d", len(docs), concurrency)

    tasks = [compile_one(client, doc, sem, progress) for doc in docs]
    results_list = await asyncio.gather(*tasks)

    results = {}
    for doc_id, result in results_list:
        if result:
            results[doc_id] = result

    logger.info(
        "Phase 1 완료: 성공 %d, 캐시 %d, 실패 %d / 총 %d",
        progress["done"],
        progress["cached"],
        progress["failed"],
        progress["total"],
    )
    if progress["verify_total"]:
        rate = progress["verify_failed"] / progress["verify_total"] * 100
        logger.info(
            "Phase 1.5 검증: %d/%d fact 실패 (%.2f%%)",
            progress["verify_failed"],
            progress["verify_total"],
            rate,
        )
    return results
