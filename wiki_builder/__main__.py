"""Wiki Builder 진입점.

새 사건이나 기존 사건에 신규 입력 파일이 생겼을 때 수동으로 실행.

사용법:
    python -m wiki_builder --case data/spark-v2              # 전체 (Phase 1-5, 7)
    python -m wiki_builder --case data/spark-v2 --phase 4   # 특정 phase
    python -m wiki_builder --case /external/case-2           # 외부 경로
"""

import argparse
import asyncio
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

import frontmatter
from dotenv import load_dotenv

# .env → os.environ 주입. config / google-genai SDK 가
# GOOGLE_APPLICATION_CREDENTIALS 등을 환경변수에서 직접 읽으므로 다른 import 보다 먼저.
load_dotenv()

from wiki_builder.config import apply_case_path, wiki_settings  # noqa: E402
from wiki_builder.observability import flush as langfuse_flush  # noqa: E402
from wiki_builder.observability import get_langfuse, get_token_stats  # noqa: E402
from wiki_builder.wiki_store import append_log, ensure_dirs, wiki_dir, write_source_page  # noqa: E402
from wiki_builder.concept_extractor import run_phase3  # noqa: E402
from wiki_builder.cross_ref import run_phase4, sanitize_wiki_pages, strip_all_wikilinks  # noqa: E402
from wiki_builder.entity_extractor import run_phase2  # noqa: E402
from wiki_builder.index_generator import run_phase5  # noqa: E402
from wiki_builder.loader import load_all_documents, sort_by_category  # noqa: E402
from wiki_builder.realtime_compiler import run_phase1_realtime  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wiki Builder")
    parser.add_argument(
        "--case",
        type=Path,
        required=True,
        help="사건 폴더 경로 (예: data/spark-v2). 하위에 json/ 입력과 wiki-output/ 출력이 위치",
    )
    parser.add_argument(
        "--phase",
        type=str,
        default="all",
        choices=["all", "1", "2", "2.5", "3", "3.5", "synth", "4", "5", "6", "7"],
        help="실행할 phase (기본: all)",
    )
    parser.add_argument(
        "--force-synth",
        action="store_true",
        help="synth phase 에서 source_count 변동 여부와 무관하게 모든 페이지 재합성",
    )
    return parser.parse_args()


def setup_logging() -> None:
    wiki_settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                wiki_settings.LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                encoding="utf-8",
            ),
        ],
    )


async def main() -> None:
    args = parse_args()
    apply_case_path(args.case)
    setup_logging()

    logger.info("=== 위키 빌더 시작 (case=%s, phase=%s) ===", args.case, args.phase)

    lf = get_langfuse()
    if lf:
        logger.info("Langfuse 연결됨: %s", wiki_settings.LANGFUSE_BASE_URL)
    else:
        logger.info("Langfuse 비활성화")

    ensure_dirs()

    # 1. 문서 로드
    logger.info("문서 로드 중: %s", wiki_settings.JSON_DIR)
    docs = await load_all_documents(wiki_settings.JSON_DIR)
    docs = sort_by_category(docs)
    logger.info("문서 로드 완료: %d개", len(docs))

    cat_counts = Counter(d.category for d in docs)
    for cat, cnt in cat_counts.most_common():
        logger.info("  %s: %d개", cat, cnt)
    logger.info("총 토큰: %d", sum(d.token_count for d in docs))

    doc_order = [d.id for d in docs]
    run_all = args.phase == "all"

    # === Phase 1: 소스 컴파일 ===
    if run_all or args.phase == "1":
        logger.info("=== Phase 1: 소스 컴파일 (실시간 API) ===")
        compile_results = await run_phase1_realtime(docs, concurrency=15)
        stats = get_token_stats()
        logger.info(
            "Phase 1 토큰: 입력 %d, 출력 %d, 호출 %d회",
            stats["total_input_tokens"],
            stats["total_output_tokens"],
            stats["total_calls"],
        )
        append_log(
            f"Phase 1: {len(compile_results)}/{len(docs)} 성공, 토큰 {stats['total_tokens']:,}"
        )

        # 소스 페이지 생성
        doc_map = {d.id: d for d in docs}
        for doc_id, result in compile_results.items():
            doc = doc_map.get(doc_id)
            if doc:
                write_source_page(
                    doc_id=doc.id,
                    title=doc.name,
                    category=doc.category,
                    person=doc.person,
                    pages=doc.total_page,
                    tokens=doc.token_count,
                    result=result,
                )
        logger.info("소스 페이지 생성 완료: %d개", len(compile_results))

    # Phase 2-5에서 필요한 compile_results 로드 (alias 정규화는 registry 만 사용해 불필요)
    if run_all or args.phase in ("2", "3", "4", "5"):
        from wiki_builder.compiler import (
            get_cached_doc_ids,
            load_compile_cache,
            parse_compile_result,
        )

        cached_ids = get_cached_doc_ids(wiki_settings.CACHE_DIR)
        compile_results = {}
        for doc_id in cached_ids:
            raw = load_compile_cache(wiki_settings.CACHE_DIR, doc_id)
            if raw:
                result = parse_compile_result(doc_id, raw)
                if result:
                    compile_results[doc_id] = result
        logger.info("캐시에서 컴파일 결과 로드: %d개", len(compile_results))

    # === Phase 2: 엔티티 점진적 성장 ===
    if run_all or args.phase == "2":
        logger.info("=== Phase 2: 엔티티 점진적 성장 ===")
        entity_registry = await run_phase2(compile_results, doc_order)
        append_log(f"Phase 2: 엔티티 {len(entity_registry.entries)}개")

    # === Phase 2.5: entity alias canonicalization ===
    if run_all or args.phase == "2.5":
        from wiki_builder.alias_resolver import run_phase2_5

        logger.info("=== Phase 2.5: entity alias canonicalization ===")
        stats25 = await run_phase2_5()
        append_log(
            f"Phase 2.5: {stats25['groups']} 그룹 병합, {stats25['absorbed']}개 흡수, registry {stats25['registry']}개"
        )

    # === Phase 3: 개념 점진적 성장 ===
    if run_all or args.phase == "3":
        logger.info("=== Phase 3: 개념 점진적 성장 ===")
        concept_registry = await run_phase3(compile_results, doc_order)
        append_log(f"Phase 3: 개념 {len(concept_registry.entries)}개")

    # === Phase 3.5: concept alias canonicalization ===
    if run_all or args.phase == "3.5":
        from wiki_builder.alias_resolver import run_phase3_5

        logger.info("=== Phase 3.5: concept alias canonicalization ===")
        stats35 = await run_phase3_5()
        append_log(
            f"Phase 3.5: {stats35['groups']} 그룹 병합, {stats35['absorbed']}개 흡수, registry {stats35['registry']}개"
        )

    # === Phase synth: entity/concept SYNTHESIS LLM 합성 ===
    if run_all or args.phase == "synth":
        from wiki_builder.synthesizer import run_synthesis

        logger.info("=== Phase synth: SYNTHESIS 합성 ===")
        synth_stats = await run_synthesis(force=args.force_synth)
        append_log(
            f"Phase synth: entity {synth_stats['entity']['synthesized']}건, "
            f"concept {synth_stats['concept']['synthesized']}건 합성"
        )

    # === Phase 4: 교차 참조 ===
    if run_all or args.phase == "4":
        logger.info("=== Phase 4: 교차 참조 ===")
        sanitized = sanitize_wiki_pages()
        logger.info("Phase 4a: sanitize %d개 페이지", sanitized)
        stripped = strip_all_wikilinks()
        logger.info("Phase 4b: strip %d개 페이지", stripped)
        modified = run_phase4()
        post_sanitized = sanitize_wiki_pages()
        if post_sanitized:
            logger.info("Phase 4d: post-sanitize %d개 페이지", post_sanitized)
        append_log(f"Phase 4: {modified}개 페이지에 교차 참조 삽입")

    # === Phase 5: Index & Overview ===
    if run_all or args.phase == "5":
        logger.info("=== Phase 5: Index & Overview ===")
        source_pages = []
        sources_dir = wiki_dir() / "sources"
        if sources_dir.exists():
            for path in sorted(sources_dir.glob("*.md")):
                post = frontmatter.load(str(path))
                meta = dict(post.metadata)
                meta["summary"] = ""
                for line in post.content.split("\n"):
                    if line.startswith("## 요약"):
                        continue
                    if line.startswith("## ") and meta["summary"]:
                        break
                    if meta.get("summary") is not None:
                        meta["summary"] += line + " "
                source_pages.append(meta)

        await run_phase5(source_pages)
        append_log("Phase 5: index.md, overview.md 생성")

    # === Phase 6: 린트 (orphan / broken link) ===
    if run_all or args.phase == "6":
        from wiki_builder.linter import run_phase6

        logger.info("=== Phase 6: 린트 ===")
        run_phase6()
        append_log("Phase 6: lint_report.md 생성")

    # === Phase 7: 임베딩 인덱스 (Hybrid 검색 Tier 2) ===
    if run_all or args.phase == "7":
        from wiki_builder.embedder import run_phase7

        logger.info("=== Phase 7: 임베딩 인덱스 빌드 ===")
        embed_stats = await run_phase7()
        append_log(
            f"Phase 7: 임베딩 {embed_stats['total']}개 "
            f"(신규 {embed_stats['new']}, 갱신 {embed_stats['updated']}, "
            f"재사용 {embed_stats['unchanged']})"
        )

    final_stats = get_token_stats()
    logger.info(
        "=== 위키 빌더 완료 === 총 토큰: 입력 %d, 출력 %d (%d회 호출)",
        final_stats["total_input_tokens"],
        final_stats["total_output_tokens"],
        final_stats["total_calls"],
    )
    langfuse_flush()


if __name__ == "__main__":
    asyncio.run(main())
