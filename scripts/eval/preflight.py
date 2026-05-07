"""위키 수치/문구 보존 사전 점검.

벤치마크 골든 답에 자주 등장하는 정확 수치·고유명사가 위키 페이지에 얼마나
보존되어 있는지 측정한다. 보존율 < 임계치면 평가 점수 신뢰도가 떨어지므로
경고를 남긴다.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CRITICAL_TERMS: tuple[str, ...] = (
    "212억",
    "192억",
    "107억",
    "92.24",
    "WACC",
    "12.26",
    "프로젝트 에르메스",
    "에르메스 딜",
    "OpenStack",
    "쪼개기 후원",
    "우호지분",
    "원진회계법인",
    "우리회계법인",
    "남충범",
    "Trading Multiple",
    "Transaction Multiple",
    "EV/Revenue",
    "Term Sheet",
    "Kick-off",
    "정필훈",
    "오승진",
    "최왕순",
    "박복수",
    "1,300억",
    "200억",
)


@dataclass
class PreflightResult:
    total_terms: int
    present_count: int
    preservation_rate: float
    passed: bool
    per_term: dict[str, int] = field(default_factory=dict)


def _grep_count(term: str, root: Path) -> int:
    try:
        result = subprocess.run(
            ["grep", "-rl", "-F", "--include=*.md", term, str(root)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("preflight: grep %r 실패 — %s", term, exc)
        return 0
    if result.returncode not in (0, 1):
        logger.warning("preflight: grep returncode=%d", result.returncode)
        return 0
    out = result.stdout.strip()
    return len(out.split("\n")) if out else 0


def check_value_preservation(case_path: str | Path, threshold: float = 0.7) -> PreflightResult:
    """``<case>/wiki-output`` 에 핵심 토큰이 얼마나 보존되어 있는지 측정."""
    case = Path(case_path)
    wiki_dir = case / "wiki-output"
    if not wiki_dir.is_dir():
        raise FileNotFoundError(f"wiki-output 디렉토리 없음: {wiki_dir}")

    per_term: dict[str, int] = {}
    for term in CRITICAL_TERMS:
        per_term[term] = _grep_count(term, wiki_dir)

    present = sum(1 for c in per_term.values() if c > 0)
    rate = present / len(CRITICAL_TERMS) if CRITICAL_TERMS else 1.0
    return PreflightResult(
        total_terms=len(CRITICAL_TERMS),
        present_count=present,
        preservation_rate=rate,
        passed=rate >= threshold,
        per_term=per_term,
    )
