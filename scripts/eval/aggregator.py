"""집계 및 리포트 생성."""

from __future__ import annotations

from collections import Counter
from typing import get_args

from .scorer import JudgeVerdict

_VERDICT_ORDER: dict[str, int] = {"오답": 0, "부분정답": 1, "정답": 2, "N/A": 3}
assert set(_VERDICT_ORDER) == set(get_args(JudgeVerdict.model_fields["verdict"].annotation)), (
    "verdict 라벨이 JudgeVerdict 와 어긋남 — _VERDICT_ORDER 갱신 필요"
)


def aggregate(items: list[dict]) -> dict:
    n = len(items)
    if n == 0:
        return {}
    counts = Counter(r["judge"]["verdict"] for r in items if r.get("judge"))
    judged = sum(counts.values())
    correct = counts["정답"]
    partial = counts["부분정답"]
    incorrect = counts["오답"]
    na = counts["N/A"]
    div = max(judged, 1)
    return {
        "judged": judged,
        "correct": correct,
        "partial": partial,
        "incorrect": incorrect,
        "na": na,
        "correct_rate": round(correct / div, 3),
        "partial_rate": round(partial / div, 3),
        "incorrect_rate": round(incorrect / div, 3),
        "correct_or_partial_rate": round((correct + partial) / div, 3),
        "avg_elapsed_s": round(sum(r.get("elapsed_s", 0) for r in items) / n, 2),
    }


def _worst_key(r: dict) -> tuple[int, int]:
    j = r["judge"]
    severity = _VERDICT_ORDER.get(j.get("verdict", "N/A"), 4)
    badness = -(len(j.get("extra_wrong", [])) + len(j.get("golden_missed", [])))
    return (severity, badness)


def to_markdown(summary: dict, results: list[dict], top_failures: int = 5) -> str:
    lines: list[str] = ["# Benchmark Eval Summary", ""]
    pf = summary["preflight"]
    lines.append(
        f"**위키 보존**: {pf['present_count']}/{pf['total_terms']} "
        f"({pf['preservation_rate'] * 100:.1f}%) — passed={pf['passed']}"
    )
    lines.append(f"**Total queries**: {summary['total']}")
    lines.append(f"**Model**: {summary['model']}")
    lines.append("")
    lines.append("## Overall")
    for k, v in summary["overall"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## By category")
    for cat, agg in sorted(summary["categories"].items()):
        lines.append(f"### {cat} ({agg['count']})")
        for k, v in agg.items():
            if k == "count":
                continue
            lines.append(f"- {k}: {v}")
        lines.append("")

    judged = [r for r in results if r.get("judge")]
    if judged:
        worst = sorted(judged, key=_worst_key)[:top_failures]
        lines.append(f"## Worst {len(worst)} (오답 → 부분정답 → 정답 → N/A)")
        for r in worst:
            j = r["judge"]
            lines.append(f"- **idx {r['idx']}** [{r['category']}] verdict={j.get('verdict', '-')}")
            lines.append(f"  - Q: {r['query']}")
            if j.get("golden_missed"):
                missed = "; ".join(j["golden_missed"][:3])
                lines.append(f"  - missed: {missed}")
            if j.get("extra_wrong"):
                wrong = "; ".join(j["extra_wrong"][:3])
                lines.append(f"  - extra_wrong: {wrong}")
            if j.get("reasoning"):
                lines.append(f"  - reasoning: {j['reasoning']}")
        lines.append("")
    return "\n".join(lines)
