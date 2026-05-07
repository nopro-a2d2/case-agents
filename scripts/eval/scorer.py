"""채점기 — v3 Direct Mode (Gemini-as-judge, holistic).

case-chatbot/chatbot/eval/scorer.py 와 동일한 판정 로직 및 호출 방식.
google-genai SDK 로 Vertex AI Gemini 를 직접 호출하고 response_schema 로
구조화된 판정 결과를 얻는다.
"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM = """\
당신은 한국 법률 사건 QA 답변을 holistic 하게 평가하는 채점관입니다. 골든 답을
ground truth 로 보고 (질문, 골든, 예측) 을 한꺼번에 보면서 사람 검토자 시각으로
판정하세요. claim 단위로 쪼개지 말고 답변 전체를 통째로 보세요.

## 판정 라벨 (verdict)
- 정답: 골든의 핵심 사실 80% 이상 커버 + extra_wrong 없음
- 부분정답: 핵심 일부 누락 또는 사실 차이가 있으나 extra_wrong 없음
- 오답: extra_wrong (거짓·골든과 충돌·별건 인물 혼동) 가 있거나 핵심 50% 이상 누락
- N/A: 시스템 답이 비었거나 오류라서 채점 불가

## 출력 6필드
- golden_covered: 골든의 핵심 사실 중 답이 담은 것 (짧은 bullet, 표현은 자유)
- golden_missed: 골든의 핵심 사실 중 답이 빠뜨린 것
- extra_correct: 골든에 없지만 답이 추가로 제공한 사실 — RAG 가 더 많은 문서를
  참조해 풍부한 정보를 답하면 강점이며 **패널티가 아님**
- extra_unverified: 출처 검증은 안 됐지만 의심스럽지 않은 정보
- extra_wrong: 거짓 / 골든과 충돌 / 별건 사건의 인물·수치 혼동
- reasoning: 위 분해를 종합한 2~3 문장 판정 사유

## 채점 원칙
- 표현 차이·길이 차이·서술 순서 차이는 무시. 사실 일치(수치·날짜·인명·관계)만 중요.
- 같은 수치를 다른 기준(예: 계약수주액 기반 vs 절대금액 기반)으로 표현했다면 둘 다
  사실이라면 covered 로 인정.
- 출처 메타정보("원진리포트에 따르면" 등)가 시스템 답에 빠진 것 자체는 missed 로
  취급하지 마세요. 사실 자체가 없을 때만 missed.
- 골든에 없는 정보를 지어내거나 별건의 사람/사건과 혼동하면 큰 감점 (extra_wrong).
"""

_JUDGE_USER_TEMPLATE = """\
[질문]
{question}

[골든 답 (ground truth)]
{golden}

[예측 답]
{predicted}

위 6필드 + verdict + reasoning 을 JSON 으로만 출력하세요. 다른 텍스트 절대 추가 금지.
"""


class JudgeVerdict(BaseModel):
    verdict: Literal["정답", "부분정답", "오답", "N/A"]
    golden_covered: list[str] = Field(default_factory=list)
    golden_missed: list[str] = Field(default_factory=list)
    extra_correct: list[str] = Field(default_factory=list)
    extra_unverified: list[str] = Field(default_factory=list)
    extra_wrong: list[str] = Field(default_factory=list)
    reasoning: str


_JUDGE_MAX_ATTEMPTS = 3
_JUDGE_BACKOFF_BASE = 0.5
_JUDGE_BACKOFF_JITTER = 0.25


def _judge_dict(
    v: JudgeVerdict | None,
    raw: str,
    attempts: int,
    error_reason: str = "",
) -> dict[str, Any]:
    if v is None:
        v = JudgeVerdict(verdict="N/A", reasoning=f"[judge_error: {error_reason}]")
    return {**v.model_dump(), "raw": raw, "attempts": attempts}


def judge_with_llm(
    question: str,
    golden: str,
    predicted: str,
    *,
    llm_client: Any,
    model: str,
) -> dict[str, Any]:
    """Gemini judge 로 holistic 판정 (v3 Direct Mode).

    case-chatbot/chatbot/eval/scorer.py 와 동일한 호출 방식.
    ``llm_client`` 는 ``genai.Client(vertexai=True, ...)`` 인스턴스,
    ``model`` 은 Vertex AI Gemini 모델 ID 문자열.
    """
    prompt = _JUDGE_USER_TEMPLATE.format(question=question, golden=golden, predicted=predicted)
    last_error = ""
    last_raw = ""

    for attempt in range(1, _JUDGE_MAX_ATTEMPTS + 1):
        try:
            response = llm_client.models.generate_content(
                model=model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config={
                    "system_instruction": _JUDGE_SYSTEM,
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                    "response_schema": JudgeVerdict,
                },
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"http_error: {exc.__class__.__name__}: {exc}"
            logger.warning("judge LLM 호출 실패 (시도 %d/%d): %s", attempt, _JUDGE_MAX_ATTEMPTS, exc)
        else:
            last_raw = (response.text or "")[:500]
            verdict = getattr(response, "parsed", None)
            if isinstance(verdict, JudgeVerdict):
                return _judge_dict(verdict, last_raw, attempt)
            try:
                parsed = JudgeVerdict.model_validate_json(response.text or "")
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = f"parse_error: {exc.__class__.__name__}: {exc}"
                logger.warning("judge 응답 파싱 실패 (시도 %d/%d): %s", attempt, _JUDGE_MAX_ATTEMPTS, exc)
            else:
                return _judge_dict(parsed, last_raw, attempt)

        if attempt < _JUDGE_MAX_ATTEMPTS:
            sleep_s = _JUDGE_BACKOFF_BASE * (2 ** (attempt - 1))
            sleep_s *= 1.0 + random.uniform(-_JUDGE_BACKOFF_JITTER, _JUDGE_BACKOFF_JITTER)
            time.sleep(max(0.0, sleep_s))

    return _judge_dict(None, last_raw, _JUDGE_MAX_ATTEMPTS, error_reason=last_error or "unknown")
