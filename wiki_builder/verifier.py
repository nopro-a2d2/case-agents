"""Phase 1.5 citation back-check.

Phase 1 LLM 출력의 인용된 fact 가 해당 페이지 raw text 에 string-level 로
존재하는지 검사한다. LLM 호출 없음 (비용 0). 환각/오인용 fact 는 분리해
source 페이지의 ``## 검증 실패`` 섹션으로 떼어 놓아 변호사가 직접 확인할 수 있게 한다.

검증 정책 (loose):
- date/amount/person/organization: 값 문자열 substring 매칭 + 숫자열 정규화 비교
- legal_provision: 문서 full_text 에서 substring 매칭 (페이지 매핑 없음)
- detailed_content: paraphrase 허용 → 의미 토큰 ≥ 40% 가 인용 페이지에 존재해야 통과
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from wiki_builder.models import CompileResult, Document

logger = logging.getLogger(__name__)

_DIGIT_RE = re.compile(r"\d+")
# 의미 있는 토큰: 2자 이상의 한글/영문/숫자 시퀀스 (citation 토큰 등 punctuation 제외)
_TOKEN_RE = re.compile(r"[\w가-힣]{2,}")
_CITATION_RE = re.compile(r"\(source-[^)]*\)")


@dataclass
class VerifyOutcome:
    total: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.failures)


def _page_text(doc: Document, page: int) -> str:
    for p in doc.content:
        if p.page == page:
            return p.text
    return ""


def _pages_text(doc: Document, pages: list[int]) -> str:
    if not pages:
        return doc.full_text
    return "\n".join(_page_text(doc, p) for p in pages)


def _normalize_digits(s: str) -> str:
    return "".join(_DIGIT_RE.findall(s))


def _verify_value(value: str, hay: str) -> bool:
    """value 문자열이 hay 안에 존재하는지 — substring 또는 숫자열 정규화 비교.

    예: "2024.03.15" 가 "2024년 3월 15일"에도 매칭 (digits "20240315" → "2024315"…
    실제로는 "2024" + "3" + "15" 순서가 보존되지 않으면 실패하지만, 적어도
    "20240315" 가 hay 의 normalized digits 에 그대로 들어 있으면 OK).
    """
    value = value.strip()
    if not value:
        return True
    if value in hay:
        return True
    digits = _normalize_digits(value)
    if digits and len(digits) >= 4 and digits in _normalize_digits(hay):
        return True
    return False


def _verify_text_overlap(text: str, hay: str, min_ratio: float = 0.4) -> bool:
    """LLM이 paraphrase 한 문장을 검증 — 의미 토큰의 일정 비율이 hay 에 존재하면 통과."""
    text = _CITATION_RE.sub("", text)
    tokens = [t for t in _TOKEN_RE.findall(text) if not (t.isdigit() and len(t) < 4)]
    if len(tokens) < 2:
        # 너무 짧은 문장은 검증 신호가 약함 → 통과 처리
        return True
    hits = sum(1 for t in tokens if t in hay)
    return hits / len(tokens) >= min_ratio


def verify_compile_result(result: CompileResult, doc: Document) -> VerifyOutcome:
    """compile result 의 모든 fact 를 검증해 실패 목록과 통계를 돌려준다."""
    outcome = VerifyOutcome()
    full = doc.full_text

    def _record(category: str, field_dict: dict, reason: str) -> None:
        outcome.failures.append(
            {"category": category, "field": field_dict, "reason": reason}
        )

    for d in result.key_facts.dates:
        outcome.total += 1
        hay = _pages_text(doc, d.pages) if d.pages else full
        if not _verify_value(d.date, hay):
            _record("date", d.model_dump(), "date string not found in cited pages")

    for a in result.key_facts.amounts:
        outcome.total += 1
        hay = _pages_text(doc, a.pages) if a.pages else full
        if not _verify_value(a.amount, hay):
            _record("amount", a.model_dump(), "amount string not found in cited pages")

    for p in result.key_facts.persons:
        outcome.total += 1
        hay = _pages_text(doc, p.pages) if p.pages else full
        if not _verify_value(p.name, hay):
            _record("person", p.model_dump(), "name not found in cited pages")

    for o in result.key_facts.organizations:
        outcome.total += 1
        hay = _pages_text(doc, o.pages) if o.pages else full
        if not _verify_value(o.name, hay):
            _record("organization", o.model_dump(), "name not found in cited pages")

    for lp in result.key_facts.legal_provisions:
        outcome.total += 1
        if not _verify_value(lp, full):
            _record(
                "legal_provision",
                {"text": lp},
                "provision string not found in document",
            )

    for s in result.detailed_content:
        outcome.total += 1
        hay = _pages_text(doc, s.pages) if s.pages else full
        if not _verify_text_overlap(s.text, hay):
            _record(
                "detailed",
                s.model_dump(),
                "low token overlap with cited pages",
            )

    return outcome
