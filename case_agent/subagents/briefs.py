"""Brief sub-agent definitions — one per Korean legal brief type.

Each sub-agent is specialized for a single brief kind and runs the full
Gather → Write → Save → Verify loop in isolation. The main agent enters
Strategy mode first, then delegates to the appropriate sub-agent via
``task(subagent_name="brief_<kind>", prompt=...)``.

All brief sub-agents use the heavy model (Sonnet) because brief drafting
requires multi-step reasoning. They share the same tool set but have
brief-type-specific system prompts derived from the base template.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.search import Embedder
    from ..workspace import Workspace

_BASE_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "brief_base_system.md"
_BASE_PROMPT_TEMPLATE = _BASE_PROMPT_PATH.read_text(encoding="utf-8")

# Per-kind specialisation: brief_requirements injected into the base template.
_BRIEF_SPECS: dict[str, dict[str, str]] = {
    "evidence_acknowledgment": {
        "brief_label": "증거인부서",
        "brief_kind": "evidence_acknowledgment",
        "completeness_kind": "evidence_acknowledgment",
        "description": (
            "Draft 증거인부서 (evidence acknowledgment) by reviewing every piece of "
            "prosecution evidence and producing a structured agree/object/partial-object "
            "table with full citation-backed rationale. Saves to briefs/."
        ),
        "brief_requirements": (
            "- 헤딩에 **'증거'** 키워드가 포함된 섹션이 필수입니다.\n"
            "- 각 증거 항목마다 **동의 / 부동의 / 일부부동의** 의견과 **이유**를 기재합니다.\n"
            "- 부동의 이유에는 형사소송법 조항(예: 제308조의2, 제312조, 제313조)과 "
            "판례 근거를 포함합니다.\n"
            "- 최소 **3개 이상** `path#anchor` 인용이 필요합니다.\n"
            "- `check_completeness('evidence_acknowledgment', path)` 로 검증합니다."
        ),
    },
    "witness_questions": {
        "brief_label": "증인심문사항",
        "brief_kind": "witness_questions",
        "completeness_kind": "witness_questions",
        "description": (
            "Draft 증인심문사항 (witness examination questions) organized by legal issues. "
            "Each issue section must have citation-backed background and at least 5 "
            "targeted questions. Saves to briefs/."
        ),
        "brief_requirements": (
            "- 헤딩에 **'증인'** 키워드가 포함된 섹션이 필수입니다.\n"
            "- 쟁점별로 섹션을 구분하고, 각 섹션에는 배경 설명(인용 포함)과 "
            "심문 사항을 포함합니다.\n"
            "- **질문은 반드시 '?'로 끝나야** 하며, 전체 5개 이상이어야 합니다.\n"
            "- 증인 진술·수사 기록의 모순을 드러내는 탄핵 질문을 반드시 포함합니다.\n"
            "- 최소 **3개 이상** `path#anchor` 인용이 필요합니다.\n"
            "- `check_completeness('witness_questions', path)` 로 검증합니다."
        ),
    },
    "defendant_questions": {
        "brief_label": "피고인심문사항",
        "brief_kind": "defendant_questions",
        "completeness_kind": "defendant_questions",
        "description": (
            "Draft 피고인심문사항 (defendant examination questions) for defense-led "
            "direct examination. Covers key factual disputes and sentencing factors "
            "with citation-backed framing. Saves to briefs/."
        ),
        "brief_requirements": (
            "- 헤딩에 **'피고인'** 키워드가 포함된 섹션이 필수입니다.\n"
            "- 공소사실 각 쟁점에 대해 피고인의 입장을 확인하는 질문을 작성합니다.\n"
            "- 정상 관련 사항(반성, 피해 회복, 생활환경 등) 섹션을 포함합니다.\n"
            "- 최소 **2개 이상** `path#anchor` 인용이 필요합니다.\n"
            "- `check_completeness('defendant_questions', path)` 로 검증합니다."
        ),
    },
    "defense_opinion": {
        "brief_label": "변호인의견서",
        "brief_kind": "defense_opinion",
        "completeness_kind": "defense_opinion",
        "description": (
            "Draft 변호인의견서 (defense attorney opinion) with a structured fact section, "
            "legal analysis per disputed issue, and a clear conclusion. All factual claims "
            "must be citation-backed. Saves to briefs/."
        ),
        "brief_requirements": (
            "- 헤딩에 **'사실관계'**, **'법리'**, **'결론'** 키워드가 포함된 섹션이 필수입니다.\n"
            "- 법리 검토 섹션은 쟁점별로 세분화하고, 각 쟁점에서 "
            "'관련 법령 → 판례·학설 → 사건 적용 → 소결' 구조를 따릅니다.\n"
            "- 검사 측 주장을 인용한 뒤 반박하는 구조를 취합니다.\n"
            "- 최소 **5개 이상** `path#anchor` 인용이 필요합니다.\n"
            "- `check_completeness('defense_opinion', path)` 로 검증합니다."
        ),
    },
    "civil_brief": {
        "brief_label": "민사준비서면",
        "brief_kind": "civil_brief",
        "completeness_kind": "civil_brief",
        "description": (
            "Draft 민사준비서면 (civil preparatory brief) following the 청구원인 → 주장 → "
            "반박 → 결론 structure. Includes citation-backed facts and legal grounds. "
            "Saves to briefs/."
        ),
        "brief_requirements": (
            "- 헤딩에 **'청구'**, **'주장'**, **'결론'** 키워드가 포함된 섹션이 필수입니다.\n"
            "- 청구원인은 계약·법률 사실관계를 시간 순서로 서술합니다.\n"
            "- 상대방 주장에 대한 반박 섹션을 별도로 구성합니다.\n"
            "- 손해액·이행 청구 금액은 `calculate` 도구로 산정하고 출처를 명시합니다.\n"
            "- 최소 **5개 이상** `path#anchor` 인용이 필요합니다.\n"
            "- `check_completeness('civil_brief', path)` 로 검증합니다."
        ),
    },
}


def _build_system_prompt(spec: dict[str, str]) -> str:
    return _BASE_PROMPT_TEMPLATE.format(**spec)


def build_brief_subagents(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, dict[str, Any]]:
    """Build one sub-agent per brief type and return a name-keyed registry.

    All brief sub-agents use the heavy model (Sonnet) when ``model`` is
    provided; otherwise the task tool falls back to its ``fallback_model``.
    Note: pass the *heavy* model here — brief writing is not a light task.
    """
    from ..tools.agent_tools import (
        build_read_with_anchor_tool,
        build_smart_search_tool,
        build_verify_citations_tool,
        build_check_completeness_tool,
        build_calculate_tool,
    )
    from ..tools.briefs import (
        build_list_brief_templates_tool,
        build_load_brief_template_tool,
        build_write_brief_tool,
    )

    shared_tools = [
        build_smart_search_tool(workspace, embedder),
        build_read_with_anchor_tool(workspace),
        build_calculate_tool(),
        build_list_brief_templates_tool(),
        build_load_brief_template_tool(),
        build_write_brief_tool(workspace),
        build_verify_citations_tool(workspace),
        build_check_completeness_tool(workspace),
    ]

    registry: dict[str, dict[str, Any]] = {}
    for kind, spec in _BRIEF_SPECS.items():
        sa_name = f"brief_{kind}"
        sa: dict[str, Any] = {
            "name": sa_name,
            "description": spec["description"],
            "system_prompt": _build_system_prompt(spec),
            "tools": shared_tools,
        }
        if model is not None:
            sa["model"] = model
        registry[sa_name] = sa

    return registry


__all__ = ["build_brief_subagents"]
