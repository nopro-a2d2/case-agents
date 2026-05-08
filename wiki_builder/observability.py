"""Langfuse 관찰성 연동 (v4 API).

Langfuse 클라이언트와 LangChain ``CallbackHandler`` 의 단일 진실은
:mod:`case_agent.observability` 가 보유한다. 이 모듈은 wiki_builder
전용 헬퍼(``log_generation``, ``log_batch_job``, ``get_session_id``,
``get_token_stats``)만 추가로 제공한다.
"""

import logging
from datetime import datetime
from typing import Any

from case_agent.observability import (
    flush as _shared_flush,
    get_langchain_callback as _shared_get_callback,
    get_langfuse as _shared_get_langfuse,
)
from wiki_builder.config import wiki_settings

logger = logging.getLogger(__name__)

_session_id: str = f"llm-wiki-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 누적 토큰 카운터
_total_input_tokens: int = 0
_total_output_tokens: int = 0
_total_calls: int = 0


def get_langfuse() -> Any | None:
    """Shared Langfuse client (env-driven)."""
    return _shared_get_langfuse()


def get_session_id() -> str:
    return _session_id


def set_session_id(case_name: str) -> None:
    """사건 이름 기반으로 session_id 재설정.

    엔트리포인트(``__main__.py``) 가 ``apply_case_path()`` 직후 호출.
    미호출 시 import 시점의 폴백(``llm-wiki-{timestamp}``) 이 유지된다.
    """
    global _session_id
    _session_id = f"{case_name}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def get_langchain_callback() -> Any | None:
    """Shared LangChain ``CallbackHandler`` singleton.

    deepagents/LangGraph ``agent.invoke(config={"callbacks": [...]})`` 에 주입하면
    노드 / 도구 / sub-agent / LLM 호출이 자동 트레이스된다.
    """
    return _shared_get_callback()


def log_generation(
    name: str,
    model: str,
    input_text: str,
    output_text: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    trace_name: str | None = None,
) -> None:
    """LLM 호출을 Langfuse generation으로 로깅 (토큰 사용량 포함)"""
    global _total_input_tokens, _total_output_tokens, _total_calls

    _total_input_tokens += input_tokens
    _total_output_tokens += output_tokens
    _total_calls += 1

    lf = get_langfuse()
    if not lf:
        return

    try:
        gen = lf.start_observation(
            name=name,
            as_type="generation",
            model=model,
            input=input_text[:1000],
            output=output_text[:2000],
            usage_details={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            metadata={
                "session_id": _session_id,
                "trace_name": trace_name or name,
            },
        )
        gen.end()
    except Exception:
        logger.warning("Langfuse 로깅 실패", exc_info=True)


def log_batch_job(
    name: str,
    total_requests: int,
    succeeded: int,
    failed: int,
) -> None:
    """배치 작업 결과를 Langfuse에 로깅"""
    lf = get_langfuse()
    if not lf:
        return

    try:
        gen = lf.start_observation(
            name=f"batch-{name}",
            as_type="generation",
            model=wiki_settings.BATCH_MODEL,
            metadata={
                "session_id": _session_id,
                "total_requests": total_requests,
                "succeeded": succeeded,
                "failed": failed,
            },
        )
        gen.end()
        lf.flush()
    except Exception:
        pass

    logger.info("Langfuse 배치: %s (성공=%d, 실패=%d)", name, succeeded, failed)


def get_token_stats() -> dict:
    """누적 토큰 통계"""
    return {
        "total_input_tokens": _total_input_tokens,
        "total_output_tokens": _total_output_tokens,
        "total_tokens": _total_input_tokens + _total_output_tokens,
        "total_calls": _total_calls,
    }


def flush() -> None:
    """Langfuse 버퍼 플러시 (shared client)"""
    _shared_flush()
