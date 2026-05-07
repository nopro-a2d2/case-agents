"""Langfuse 관찰성 연동 (v4 API)"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from wiki_builder.config import wiki_settings

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = logging.getLogger(__name__)

_langfuse: "Langfuse | None" = None
_langchain_handler: Any | None = None  # CallbackHandler — lazy import 로 v4 의존성 격리
_session_id: str = f"llm-wiki-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 누적 토큰 카운터
_total_input_tokens: int = 0
_total_output_tokens: int = 0
_total_calls: int = 0


def get_langfuse() -> Any:
    global _langfuse
    if not wiki_settings.LANGFUSE_ENABLED:
        return None
    if _langfuse is None:
        try:
            from langfuse import Langfuse
            _langfuse = Langfuse(
                public_key=wiki_settings.LANGFUSE_PUBLIC_KEY,
                secret_key=wiki_settings.LANGFUSE_SECRET_KEY,
                host=wiki_settings.LANGFUSE_BASE_URL,
            )
            _langfuse.auth_check()
            logger.info("Langfuse 연결 완료: %s", wiki_settings.LANGFUSE_BASE_URL)
        except Exception:
            logger.warning("Langfuse 연결 실패", exc_info=True)
            _langfuse = None
            return None
    return _langfuse


def get_session_id() -> str:
    return _session_id


def get_langchain_callback() -> Any | None:
    """Langfuse v4 LangChain ``CallbackHandler`` 의 process singleton.

    deepagents/LangGraph ``agent.invoke(config={"callbacks": [...]})`` 에 주입하면
    노드 / 도구 / sub-agent / LLM 호출이 자동 트레이스된다.
    ``LANGFUSE_ENABLED=False`` 또는 SDK / client 초기화 실패 시 ``None`` 반환 —
    호출자는 ``None`` 이면 callback 키 자체를 omit 해 zero overhead 유지.
    """
    global _langchain_handler
    if not wiki_settings.LANGFUSE_ENABLED:
        return None
    if _langchain_handler is not None:
        return _langchain_handler
    # ambient client (get_client()) 가 CallbackHandler 인스턴스 생성에 필요.
    if get_langfuse() is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        logger.warning(
            "Langfuse LangChain integration import 실패 — `langfuse[langchain]` 설치 필요"
        )
        return None
    try:
        _langchain_handler = CallbackHandler()
    except Exception:
        logger.warning("Langfuse CallbackHandler 생성 실패", exc_info=True)
        return None
    return _langchain_handler


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
    """Langfuse 버퍼 플러시"""
    lf = get_langfuse()
    if lf:
        lf.flush()
