"""check_completeness rules for the supported brief doctypes.

Mirrors :mod:`tests.test_verify` but exercises the brief doctypes
(``civil_brief``, ``general_brief``) and their body rules. Uses the ``spark``
case fixture so the workspace already has json/1.json available for citation
resolution — but completeness checks themselves do not need citation files to
resolve, so we use placeholder anchors when convenient.
"""

from __future__ import annotations

import pytest

from case_agent.tools.verify import check_completeness
from case_agent.workspace import LocalFS

CASE_ID = "spark"


@pytest.fixture()
def ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


_UNIQUE_CITES = (
    "(@@[1a])",
    "(@@[1b])",
    "(@@[1c])",
    "(@@[10a])",
    "(@@[10b])",
    "(@@[10c])",
)


def _cite_block(n: int, *, start: int = 0) -> str:
    """N **unique** citations starting at offset ``start``.

    verify._iter_ids dedups by id, so callers that emit citations in
    multiple sections must pass distinct ``start`` offsets to avoid collisions.
    """
    end = start + n
    if end > len(_UNIQUE_CITES):
        raise ValueError(f"asked for {end} unique citations, only {len(_UNIQUE_CITES)} available")
    return " ".join(_UNIQUE_CITES[start:end])


# ---------------------------------------------------------------------------
# civil_brief
# ---------------------------------------------------------------------------


def test_civil_brief_passes_with_required_sections_and_citations(ws: LocalFS) -> None:
    p = "briefs/_test_civil_pass.md"
    body = (
        "# 준비서면\n\n"
        "## 청구취지\n원고 청구 요지.\n\n"
        "## 주장\n사실 1 " + _cite_block(5) + "\n\n"
        "## 결론\n청구 인용을 구합니다.\n"
    )
    ws.write(p, body)
    rep = check_completeness(ws, "civil_brief", p)
    assert rep.ok, f"unexpected issues: {rep.issues}"


def test_civil_brief_fails_without_required_section(ws: LocalFS) -> None:
    p = "briefs/_test_civil_fail.md"
    ws.write(p, "## 청구취지\n.\n## 주장\n" + _cite_block(5) + "\n")
    rep = check_completeness(ws, "civil_brief", p)
    assert not rep.ok
    rules = {i.rule for i in rep.issues}
    assert "required_heading:결론" in rules


# ---------------------------------------------------------------------------
# general_brief — 헤딩 강제 없음, min_citations >= 3 만
# ---------------------------------------------------------------------------


def test_general_brief_passes_with_min_citations_only(ws: LocalFS) -> None:
    """범용 서면은 헤딩 키워드 강제가 없어 임의 섹션 구성으로도 통과한다."""
    p = "briefs/_test_general_pass.md"
    body = (
        "## 사건 개요\n사실 진술. " + _cite_block(2) + "\n\n"
        "## 주된 주장\n반박 논리. " + _cite_block(1, start=2) + "\n"
    )
    ws.write(p, body)
    rep = check_completeness(ws, "general_brief", p)
    assert rep.ok, f"unexpected issues: {rep.issues}"


def test_general_brief_fails_under_min_citations(ws: LocalFS) -> None:
    p = "briefs/_test_general_fail.md"
    ws.write(p, "## 본문\n인용 부족. " + _cite_block(2) + "\n")
    rep = check_completeness(ws, "general_brief", p)
    rules = {i.rule for i in rep.issues}
    assert "min_citations" in rules
