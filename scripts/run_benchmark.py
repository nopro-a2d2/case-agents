"""벤치마크 평가 진입점.

usage:
    python scripts/run_benchmark.py --case data/spark
    python scripts/run_benchmark.py --case data/spark --limit 5
    python scripts/run_benchmark.py --case data/spark --no-judge
    python scripts/run_benchmark.py --case data/spark --resume data/spark/eval-output/20260505T172345Z

설계 노트:
- 매 query 결과는 results.jsonl 에 즉시 append 되어 hang/crash 시에도 부분 결과를 보존한다.
- --resume <out_dir> 로 기존 results.jsonl 의 idx 들을 skip 하고 이어 실행 가능.
- --per-query-timeout (기본 600초) 으로 각 agent 호출에 wall-clock timeout 적용.
- asyncio.run() 을 ThreadPoolExecutor 스레드 안에서 호출해 hang 시 timeout 으로 격리.
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures as cf
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

# scripts/ 폴더를 패키지로 인식시키기 위해 sys.path 조정
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.eval.aggregator import aggregate, to_markdown
from scripts.eval.preflight import check_value_preservation
from scripts.eval.scorer import JudgeVerdict, judge_with_llm

logger = logging.getLogger("benchmark")

_VERDICT_ORDER: dict[str, int] = {"오답": 0, "부분정답": 1, "정답": 2, "N/A": 3}
assert set(_VERDICT_ORDER) == set(get_args(JudgeVerdict.model_fields["verdict"].annotation))


def _model_name(model: object) -> str:
    for attr in ("model", "model_name", "model_id"):
        val = getattr(model, attr, None)
        if isinstance(val, str) and val:
            return val
    return type(model).__name__


def _run_agent(query: str, components) -> str:
    """ThreadPoolExecutor 스레드 안에서 async agent 를 실행."""
    from case_agent.loop.runner import run_query_oneshot

    return asyncio.run(run_query_oneshot(query, components))


def main() -> int:
    parser = argparse.ArgumentParser(description="Case-Agent benchmark evaluator")
    parser.add_argument(
        "--case", required=True, type=Path, help="사건 폴더 경로 (예: data/spark)"
    )
    parser.add_argument("--limit", type=int, default=0, help="첫 N문항만 채점 (0=전체)")
    parser.add_argument(
        "--idx",
        type=str,
        default=None,
        help="평가할 query idx를 쉼표로 지정 (예: 0,3,7). --limit 보다 우선 적용.",
    )
    parser.add_argument("--no-judge", action="store_true", help="LLM judge 건너뛰기")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="결과 저장 디렉토리. 기본: <case>/eval-output/<timestamp>",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="기존 out_dir 을 받아 results.jsonl 의 idx 는 skip 하고 이어 실행.",
    )
    parser.add_argument(
        "--per-query-timeout",
        type=float,
        default=1000.0,
        help="단일 query 의 agent 호출 wall-clock timeout(초). 기본 1000s.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    case_path = args.case.resolve()

    # 0. 사전 점검
    pf = check_value_preservation(case_path)
    logger.info(
        "preflight: %d/%d (%.1f%%) passed=%s",
        pf.present_count,
        pf.total_terms,
        pf.preservation_rate * 100,
        pf.passed,
    )
    if not pf.passed:
        logger.warning("위키 보존율이 낮습니다. 평가 신뢰도가 떨어질 수 있습니다.")

    # 1. 벤치마크 로드
    benchmark_path = case_path / "benchmark" / "benchmark_indictment.json"
    if not benchmark_path.is_file():
        logger.error("벤치마크 파일 없음: %s", benchmark_path)
        return 2
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    queries = list(benchmark["queries"])
    if args.idx is not None:
        target_idxs = {int(x.strip()) for x in args.idx.split(",")}
        queries = [q for q in queries if int(q["idx"]) in target_idxs]
    elif args.limit > 0:
        queries = queries[: args.limit]
    logger.info(
        "벤치마크: %d문항 채점 (전체 %d)", len(queries), benchmark["metadata"]["total_queries"]
    )

    # 2. Agent components + judge client 초기화
    from case_agent._env import load_env
    from case_agent.agent import build_case_agent_components
    from case_agent.model.vertex import DEFAULT_LIGHT_MODEL, DEFAULT_LOCATION
    from case_agent.workspace import LocalFS

    load_env()

    root = str(case_path.parent)
    case_id = case_path.name
    ws = LocalFS(case_id=case_id, root=root)
    components = build_case_agent_components(ws)
    model_name = _model_name(components.model)

    judge_client = None
    judge_model = DEFAULT_LIGHT_MODEL
    if not args.no_judge:
        import os

        from google import genai
        from google.genai import types

        project = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        location = os.environ.get("VERTEX_LOCATION", DEFAULT_LOCATION)
        judge_client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    initial_delay=1.0,
                    max_delay=60.0,
                    exp_base=2.0,
                    jitter=1.0,
                    attempts=5,
                    http_status_codes=[408, 429, 500, 502, 503, 504],
                ),
                timeout=120 * 1000,
            ),
        )

    # 3. 채점 루프
    out_dir = (
        args.resume
        or args.out_dir
        or (case_path / "eval-output" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("결과 저장 위치: %s (resume=%s)", out_dir, bool(args.resume))

    results_jsonl = out_dir / "results.jsonl"
    results: list[dict] = []
    done_idxs: set[int] = set()
    if args.resume and results_jsonl.exists():
        for line in results_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("results.jsonl 손상 라인 1줄 skip")
                continue
            results.append(r)
            done_idxs.add(int(r["idx"]))
        logger.info(
            "resume: 기존 %d 결과 로드 → idx %s skip 예정",
            len(results),
            sorted(done_idxs)[:10],
        )

    executor = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="eval-agent")
    try:
        for i, q in enumerate(queries, 1):
            if int(q["idx"]) in done_idxs:
                continue
            logger.info("[%d/%d] (%s) %s", i, len(queries), q["category"], q["query"][:80])
            t0 = time.time()
            answer = ""
            error: str | None = None
            try:
                future = executor.submit(_run_agent, q["query"], components)
                answer = future.result(timeout=args.per_query_timeout)
            except cf.TimeoutError:
                error = f"timeout(>{args.per_query_timeout:.0f}s)"
                logger.warning("query timeout: idx=%s", q["idx"])
            except Exception as exc:  # noqa: BLE001
                error = f"agent_failed: {exc.__class__.__name__}: {exc}"
                logger.warning("agent 실패: %s", exc)
            elapsed = round(time.time() - t0, 2)

            judge: dict | None = None
            if judge_client is not None and not error:
                judge = judge_with_llm(
                    q["query"],
                    q["golden_answer"],
                    answer,
                    llm_client=judge_client,
                    model=judge_model,
                )

            result = {
                "idx": q["idx"],
                "category": q["category"],
                "query": q["query"],
                "answer": answer,
                "error": error,
                "elapsed_s": elapsed,
                "judge": judge,
                "expected_doc_idxs": q["document_idxs"],
            }
            results.append(result)

            with results_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

            logger.info(
                "  → verdict=%s elapsed=%.1fs%s",
                (judge["verdict"] if judge else "-"),
                elapsed,
                f" [{error}]" if error else "",
            )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # 4. 집계
    by_cat: dict[str, list[dict]] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    summary = {
        "preflight": {
            "present_count": pf.present_count,
            "total_terms": pf.total_terms,
            "preservation_rate": pf.preservation_rate,
            "passed": pf.passed,
        },
        "total": len(results),
        "model": model_name,
        "categories": {
            cat: {"count": len(items), **aggregate(items)} for cat, items in by_cat.items()
        },
        "overall": aggregate(results),
    }

    # 5. 저장
    (out_dir / "report.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_md = to_markdown(summary, results)
    (out_dir / "summary.md").write_text(summary_md, encoding="utf-8")
    print()
    print(summary_md)
    logger.info("✓ 결과 저장: %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
