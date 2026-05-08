"""Brief-writing sub-agents: one specialist per Korean legal brief type."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..prompts import BRIEF_BASE_SYSTEM_PROMPT
from ..tools.agent_tools import (
    build_check_completeness_tool,
    build_read_with_anchor_tool,
    build_smart_search_tool,
    build_verify_citations_tool,
)
from ..tools.briefs import (
    build_get_brief_template_tool,
    build_write_brief_tool,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.search import Embedder
    from ..workspace import Workspace

# Specialization note appended to the base system prompt for each brief type.
_SPECIALIZATIONS: dict[str, str] = {
    "brief_증거인부서": (
        "## 전문 분야: 증거인부서\n\n"
        "증거인부서 작성 시 다음에 집중하세요:\n"
        "- 검사 제출 증거 목록 전체를 확인하고 각각에 대해 증거능력·증명력 인부 표시\n"
        "- 위법수집·전문증거·임의성 없는 자백 등 증거능력 부정 사유는 법적 근거와 함께 상세 기재\n"
        "- `check_completeness('evidence_acknowledgment', path)` 로 검증\n"
    ),
    "brief_증인심문사항": (
        "## 전문 분야: 증인심문사항\n\n"
        "증인심문사항 작성 시 다음에 집중하세요:\n"
        "- 변호인 측에 유리한 사실을 끌어내는 주신문 질문 구성\n"
        "- 증인과 쟁점의 연관성을 명시하고 예상 반대신문 대비\n"
        "- `check_completeness('witness_questions', path)` 로 검증\n"
    ),
    "brief_피고인심문사항": (
        "## 전문 분야: 피고인심문사항\n\n"
        "피고인심문사항 작성 시 다음에 집중하세요:\n"
        "- 공소사실 부인 또는 정상 참작을 위한 질문 구성\n"
        "- 피고인의 동기·경위 해명과 재범 방지 의지 확인\n"
        "- `check_completeness('defendant_questions', path)` 로 검증\n"
    ),
    "brief_변호인의견서": (
        "## 전문 분야: 변호인의견서\n\n"
        "변호인의견서 작성 시 다음에 집중하세요:\n"
        "- 쟁점별 사실관계·법리·소결 구조 준수\n"
        "- 판례·법령은 반드시 실제 자료에서 인용(번호 임의 생성 금지)\n"
        "- `check_completeness('defense_opinion', path)` 로 검증\n"
    ),
    "brief_준비서면": (
        "## 전문 분야: 민사 준비서면\n\n"
        "준비서면 작성 시 다음에 집중하세요:\n"
        "- 청구원인·항변·재항변 구조를 명확히 하고 각 주장에 증거 번호 인용\n"
        "- 상대방 주장에 대한 구체적 반박과 법적 근거 제시\n"
        "- `check_completeness('civil_brief', path)` 로 검증\n"
    ),
}


def _build_brief_subagent(
    name: str,
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, Any]:
    tools: list[Any] = [
        build_smart_search_tool(workspace, embedder),
        build_read_with_anchor_tool(workspace),
        build_verify_citations_tool(workspace),
        build_check_completeness_tool(workspace),
        build_get_brief_template_tool(),
        build_write_brief_tool(workspace),
    ]
    brief_type = name.replace("brief_", "")
    specialization = _SPECIALIZATIONS.get(name, "")
    system_prompt = f"{BRIEF_BASE_SYSTEM_PROMPT}\n\n{specialization}"

    sa: dict[str, Any] = {
        "name": name,
        "description": f"한국 법률 서면 작성 전문 에이전트: {brief_type}. 사건 자료를 분석하고 표준 양식에 맞는 {brief_type}를 작성하여 briefs/ 디렉토리에 저장합니다.",
        "system_prompt": system_prompt,
        "tools": tools,
    }
    if model is not None:
        sa["model"] = model
    return sa


def build_brief_subagents(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, dict[str, Any]]:
    """Build all brief-writing sub-agents, keyed by name."""
    return {
        name: _build_brief_subagent(name, workspace, embedder, model=model)
        for name in _SPECIALIZATIONS
    }
