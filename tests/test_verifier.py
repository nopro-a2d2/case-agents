"""verifier.verify_compile_result 단위 테스트.

string-level back-check 의 핵심 케이스: substring/숫자 정규화/paraphrase 허용/실패.
"""

from __future__ import annotations

from wiki_builder.models import (
    AmountFact,
    CompileResult,
    DateFact,
    DetailedSentence,
    KeyFacts,
    OrgFact,
    PageContent,
    PersonFact,
    Document,
)
from wiki_builder.verifier import verify_compile_result


def _doc(pages: dict[int, str]) -> Document:
    return Document(
        id="X",
        name="테스트 문서",
        summary="요약",
        total_page=len(pages),
        token_count=100,
        category="공소장",
        person=None,
        content=[PageContent(page=p, text=t) for p, t in sorted(pages.items())],
    )


def _result(
    *,
    dates: list[DateFact] | None = None,
    amounts: list[AmountFact] | None = None,
    persons: list[PersonFact] | None = None,
    organizations: list[OrgFact] | None = None,
    legal_provisions: list[str] | None = None,
    detailed: list[DetailedSentence] | None = None,
) -> CompileResult:
    return CompileResult(
        doc_id="X",
        summary="요약",
        key_facts=KeyFacts(
            dates=dates or [],
            amounts=amounts or [],
            persons=persons or [],
            organizations=organizations or [],
            legal_provisions=legal_provisions or [],
        ),
        detailed_content=detailed or [],
        entities=[],
        concepts=[],
    )


def test_date_passes_when_substring_present() -> None:
    doc = _doc({1: "사건은 2024.03.15에 발생했다."})
    result = _result(dates=[DateFact(date="2024.03.15", event="사건 발생", pages=[1])])
    out = verify_compile_result(result, doc)
    assert out.failed == 0


def test_date_passes_via_digit_normalization() -> None:
    """LLM 이 '2024.03.15' 로 출력했지만 원문은 '20240315' 형식인 경우 OK."""
    doc = _doc({1: "사건일자: 20240315 송금 완료"})
    result = _result(dates=[DateFact(date="2024.03.15", event="사건", pages=[1])])
    out = verify_compile_result(result, doc)
    assert out.failed == 0


def test_date_fails_on_wrong_page_citation() -> None:
    doc = _doc({1: "다른 사건 내용", 2: "2024.03.15 송금"})
    # LLM 이 p.1 로 잘못 인용
    result = _result(dates=[DateFact(date="2024.03.15", event="송금", pages=[1])])
    out = verify_compile_result(result, doc)
    assert out.failed == 1
    assert out.failures[0]["category"] == "date"


def test_amount_substring_match() -> None:
    doc = _doc({1: "피고인은 5억원을 송금받았다."})
    result = _result(amounts=[AmountFact(amount="5억", context="송금", pages=[1])])
    out = verify_compile_result(result, doc)
    assert out.failed == 0


def test_person_name_match() -> None:
    doc = _doc({1: "피고인 윤경림은 ..."})
    result = _result(persons=[PersonFact(name="윤경림", role="피고인", pages=[1])])
    out = verify_compile_result(result, doc)
    assert out.failed == 0


def test_organization_missing_from_cited_page() -> None:
    doc = _doc({1: "그 회사는 ...", 2: "KT 그룹의 ..."})
    result = _result(organizations=[OrgFact(name="KT", role="피해자", pages=[1])])
    out = verify_compile_result(result, doc)
    assert out.failed == 1


def test_legal_provision_searched_in_full_text() -> None:
    doc = _doc({1: "범행 사실은 ...", 2: "형법 제356조 위반"})
    result = _result(legal_provisions=["형법 제356조"])
    out = verify_compile_result(result, doc)
    assert out.failed == 0


def test_detailed_paraphrase_passes_with_overlap() -> None:
    doc = _doc({1: "윤경림 피고인은 KT 사장으로 재직하면서 5억원을 횡령했다."})
    # paraphrased
    result = _result(
        detailed=[
            DetailedSentence(text="윤경림이 KT 사장 재직 중 5억원을 횡령함.", pages=[1])
        ]
    )
    out = verify_compile_result(result, doc)
    assert out.failed == 0


def test_detailed_fails_when_no_overlap() -> None:
    doc = _doc({1: "전혀 다른 내용입니다."})
    result = _result(
        detailed=[
            DetailedSentence(text="윤경림이 KT 사장 재직 중 5억원을 횡령함.", pages=[1])
        ]
    )
    out = verify_compile_result(result, doc)
    assert out.failed == 1
    assert out.failures[0]["category"] == "detailed"


def test_short_detailed_skipped() -> None:
    """토큰이 너무 적은 문장은 검증 신호가 약해 통과시킨다."""
    doc = _doc({1: "전혀 무관한 텍스트"})
    result = _result(detailed=[DetailedSentence(text="OK.", pages=[1])])
    out = verify_compile_result(result, doc)
    assert out.failed == 0


def test_total_count_matches_inputs() -> None:
    doc = _doc({1: "A B C"})
    result = _result(
        dates=[DateFact(date="2024.01.01", event="x", pages=[1])],
        amounts=[AmountFact(amount="1억", context="x", pages=[1])],
        persons=[PersonFact(name="홍길동", role="x", pages=[1])],
    )
    out = verify_compile_result(result, doc)
    assert out.total == 3
