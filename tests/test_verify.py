"""Tests for verify_citations and check_completeness."""

from __future__ import annotations

import pytest

from case_agent.tools.verify import (
    INLINE_CITE_RE,
    check_completeness,
    verify_citations,
)
from case_agent.workspace import LocalFS


CASE_ID = "spark"


@pytest.fixture()
def ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


def test_inline_cite_regex_finds_doc_ids() -> None:
    md = (
        "본 사건의 고발장에 따르면 (@@[1]) 임의제출이 있었습니다. "
        "관련 개념은 @@[cdoc_01KKH4TTAG000000000000000S] 에 정의됨."
    )
    hits = INLINE_CITE_RE.findall(md)
    assert "1" in hits
    assert "cdoc_01KKH4TTAG000000000000000S" in hits


def test_inline_cite_regex_ignores_old_grammar() -> None:
    md = "고발장 1쪽 (json/1.json#p1) 참조."
    hits = INLINE_CITE_RE.findall(md)
    assert hits == []


def test_verify_citations_all_pass(ws: LocalFS) -> None:
    p = "artifacts/_verify_pass.md"
    ws.write(
        p,
        "# 테스트\n"
        "고발장 (@@[1]) 참조.\n"
        "또 다른 자료 @@[2] 도 같이 본다.\n",
    )
    rep = verify_citations(ws, p)
    assert rep.total == 2
    assert rep.failed == 0
    assert rep.ok is True


def test_verify_citations_catches_unknown_doc_id(ws: LocalFS) -> None:
    p = "artifacts/_verify_fail.md"
    ws.write(
        p,
        "정상: @@[1].\n"
        "존재하지 않음: @@[no-such-id].\n",
    )
    rep = verify_citations(ws, p)
    assert rep.total == 2
    assert rep.failed == 1
    failed = {r.citation for r in rep.reports if not r.ok}
    assert "@@[no-such-id]" in failed


def test_check_completeness_evidence_acknowledgment_passes(ws: LocalFS) -> None:
    p = "drafts/_evidence_ack_v1.md"
    body = (
        "# 증거인부서\n\n"
        "## 증거 1호 - 고발장\n"
        "동의\n이유: 진정성립 다툼 없음 (@@[1])\n\n"
        "## 증거 2호 - 진술서\n"
        "부동의\n이유: 임의성 다툼 (@@[2])\n\n"
        "## 증거 3호 - 보고서\n"
        "일부 부동의\n이유: 일부 페이지 출처 불명 (@@[3])\n"
    )
    ws.write(p, body)
    rep = check_completeness(ws, "evidence_acknowledgment", p)
    assert rep.ok, f"unexpected issues: {rep.issues}"


def test_check_completeness_evidence_acknowledgment_misses(ws: LocalFS) -> None:
    p = "drafts/_evidence_ack_bad.md"
    ws.write(
        p,
        "# 증거인부서\n## 증거 1호\n"
        "단순 메모만 있고 동의/부동의 결정 없음.\n",
    )
    rep = check_completeness(ws, "evidence_acknowledgment", p)
    assert not rep.ok
    rule_names = {i.rule for i in rep.issues}
    assert "decision_per_evidence" in rule_names
    assert "min_citations" in rule_names


def test_check_completeness_witness_questions(ws: LocalFS) -> None:
    p = "drafts/_witness_v1.md"
    ws.write(
        p,
        "# 증인 김OO 심문사항\n"
        "## 쟁점 1: 임의제출의 임의성\n"
        "1. 제출 당시 강압이 있었습니까? (@@[1])\n"
        "2. 변호인 동석 여부는? (@@[2])\n"
        "3. 제출 동의서를 직접 작성했습니까? (@@[3])\n"
        "## 쟁점 2: 자료 범위\n"
        "4. 제출 대상이 어디까지였습니까?\n"
        "5. 별건 활용에 동의했습니까?\n",
    )
    rep = check_completeness(ws, "witness_questions", p)
    assert rep.ok, f"unexpected issues: {rep.issues}"


def test_check_completeness_unknown_kind_raises(ws: LocalFS) -> None:
    with pytest.raises(ValueError):
        check_completeness(ws, "not_a_kind", "drafts/_witness_v1.md")
