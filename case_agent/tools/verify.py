"""Verify-phase tools: citation validity + per-doctype completeness.

Citation grammar (matches `tools/citation.py`):
    `@@[id]` — single id token. No path, no anchor.

`verify_citations(path)` walks an artifact/draft, finds every `@@[id]` token,
and checks that each id exists in the workspace evidence registry. Returns a
per-citation pass/fail report; failures are surfaced for the agent to loop
back into Take Action.

`check_completeness(kind, path)` runs a doctype-specific structural checklist
(증거인부서, 증인심문사항, 변호인의견서, etc.) and returns missing-section /
missing-field hints.

Both are read-only and side-effect free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from case_agent.tools.citation import build_id_registry
from case_agent.workspace import Workspace

# Inline citation token matching `@@[id]`.
INLINE_CITE_RE = re.compile(r"@@\[([^\]\s]+)\]")


# ---------------------------------------------------------------------------
# verify_citations
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CitationReport:
    citation: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict:
        d = {"citation": self.citation, "ok": self.ok}
        if self.error:
            d["error"] = self.error
        return d


@dataclass(slots=True)
class VerifyCitationsResult:
    path: str
    total: int
    failed: int
    reports: list[CitationReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "total": self.total,
            "failed": self.failed,
            "ok": self.ok,
            "reports": [r.to_dict() for r in self.reports],
        }


def _iter_ids(text: str) -> Iterable[str]:
    seen: set[str] = set()
    for m in INLINE_CITE_RE.finditer(text):
        did = m.group(1)
        if did not in seen:
            seen.add(did)
            yield did


def verify_citations(ws: Workspace, path: str) -> VerifyCitationsResult:
    """Walk an artifact/draft and verify every embedded `@@[id]` token."""
    text = ws.read(path)
    reports: list[CitationReport] = []
    registry = build_id_registry(ws)
    for did in _iter_ids(text):
        cite = f"@@[{did}]"
        if did in registry:
            reports.append(CitationReport(citation=cite, ok=True))
        else:
            reports.append(
                CitationReport(
                    citation=cite, ok=False, error=f"unknown id: {did!r}"
                )
            )
    failed = sum(1 for r in reports if not r.ok)
    return VerifyCitationsResult(
        path=path, total=len(reports), failed=failed, reports=reports
    )


# ---------------------------------------------------------------------------
# check_completeness
# ---------------------------------------------------------------------------


DocKind = Literal[
    "evidence_acknowledgment",  # 증거인부서
    "witness_questions",        # 증인심문사항
    "defendant_questions",      # 피고인심문사항
    "civil_brief",              # 민사 준비서면 (briefs/)
    "general_brief",            # 범용 서면 (briefs/) — 헤딩 강제 없음
    "evidence_pros_cons",       # 증거 유불리표 (artifact)
    "timeline",                 # 연표 (artifact)
    "issues",                   # 쟁점표 (artifact)
]


# Per-kind required headings (literal, case-sensitive). The check is "at least
# one heading line contains this string". Keeps the schema permissive but enough
# to catch obvious gaps.
# Required heading keywords — kept minimal. Each entry is keywords that should
# appear *somewhere in any heading*. Body-level structural checks (decisions,
# question count, citation count) live in `_BODY_RULES` instead — they tolerate
# the flexibility of real legal briefs (numbered lists, label-style "이유:" etc.).
_REQUIRED_HEADINGS: dict[str, tuple[str, ...]] = {
    "evidence_acknowledgment": ("증거",),
    "witness_questions": ("증인",),
    "defendant_questions": ("피고인",),
    "civil_brief": ("청구", "주장", "결론"),
    "general_brief": (),
    "evidence_pros_cons": ("증거",),
    "timeline": (),
    "issues": ("쟁점",),
}


# Per-kind body invariants — each is `(rule_name, predicate(text)->bool, hint)`.
# Predicates are intentionally light; verify_citations covers citation health.
def _has_min_citations(text: str, n: int) -> bool:
    return sum(1 for _ in _iter_ids(text)) >= n


_DECISION_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(일부\s*부동의|부동의|동의)\s*$",
    re.MULTILINE,
)


def _evidence_table_complete(text: str) -> bool:
    """For 증거인부서: every decision line should have a paired 이유 line.

    A decision is a line whose only content (modulo bullet) is one of
    동의 / 부동의 / 일부부동의. Each decision must be paired with at least
    one '이유' marker in the body so the rationale is auditable.
    """
    if "증거" not in text:
        return False
    decisions = len(_DECISION_LINE_RE.findall(text))
    reasons = text.count("이유")
    return decisions > 0 and reasons >= decisions


def _witness_questions_have_q_mark(text: str) -> bool:
    return text.count("?") >= 5 or text.count("질문") >= 5


_BODY_RULES: dict[str, list[tuple[str, callable, str]]] = {
    "evidence_acknowledgment": [
        ("decision_per_evidence", _evidence_table_complete,
         "각 증거 항목에 동의/부동의/일부부동의 + 이유가 명시되어야 합니다."),
        ("min_citations", lambda t: _has_min_citations(t, 3),
         "최소 3개 이상의 인용(`@@[id]`)이 필요합니다."),
    ],
    "witness_questions": [
        ("has_questions", _witness_questions_have_q_mark,
         "질문이 5개 이상 있어야 합니다(? 또는 '질문' 마커)."),
        ("min_citations", lambda t: _has_min_citations(t, 3),
         "쟁점·진술 모순을 뒷받침할 인용이 최소 3개 필요합니다."),
    ],
    "defendant_questions": [
        ("min_citations", lambda t: _has_min_citations(t, 2), "최소 2개 인용 필요."),
    ],
    "civil_brief": [
        ("min_citations", lambda t: _has_min_citations(t, 5), "최소 5개 인용 필요."),
    ],
    "general_brief": [
        ("min_citations", lambda t: _has_min_citations(t, 3), "최소 3개 인용 필요."),
    ],
    "evidence_pros_cons": [
        ("min_citations", lambda t: _has_min_citations(t, 3), "최소 3개 인용 필요."),
    ],
    "timeline": [
        ("min_citations", lambda t: _has_min_citations(t, 3),
         "타임라인 항목 다수에 인용이 필요합니다."),
    ],
    "issues": [],
}


@dataclass(slots=True)
class CompletenessIssue:
    rule: str
    severity: Literal["missing_section", "rule_violation"]
    detail: str

    def to_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "detail": self.detail}


@dataclass(slots=True)
class CompletenessResult:
    path: str
    kind: str
    issues: list[CompletenessIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "ok": self.ok,
            "issues": [i.to_dict() for i in self.issues],
        }


def check_completeness(ws: Workspace, kind: str, path: str) -> CompletenessResult:
    if kind not in _REQUIRED_HEADINGS:
        raise ValueError(
            f"unknown kind: {kind!r}. Valid: {sorted(_REQUIRED_HEADINGS)}"
        )
    text = ws.read(path)
    issues: list[CompletenessIssue] = []

    # 1) heading presence
    heading_lines = [
        re.sub(r"^#+\s+", "", line).strip()
        for line in text.splitlines()
        if re.match(r"^#{1,6}\s+", line)
    ]
    joined_headings = " | ".join(heading_lines)
    for required in _REQUIRED_HEADINGS[kind]:
        if required not in joined_headings:
            issues.append(
                CompletenessIssue(
                    rule=f"required_heading:{required}",
                    severity="missing_section",
                    detail=f"필수 섹션 키워드 '{required}' 가 헤딩에 없습니다.",
                )
            )

    # 2) body rules
    for rule_name, predicate, hint in _BODY_RULES.get(kind, ()):
        if not predicate(text):
            issues.append(
                CompletenessIssue(
                    rule=rule_name, severity="rule_violation", detail=hint
                )
            )

    return CompletenessResult(path=path, kind=kind, issues=issues)
