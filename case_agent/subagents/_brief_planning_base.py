"""Common base for kind-specific BriefPlanningAgent subagents.

Mirror of :mod:`._brief_base` for the **planning** half of Brief Mode. Each
``brief_planning_<kind>`` module defines an ``EXTRA`` prompt with kind-specific
strategy guidance and calls :func:`build_brief_planning_subagent_dict`.

The planner is READ-ONLY: it never writes files. It produces ONE final message
— a JSON object — that the main agent passes to ``propose_brief_outline(...)``.

Delegation pattern:
- Main agent calls ``enter_brief_mode(kind)`` and then
  ``task(subagent_name=<planner>, ...)`` (planner name from ``BriefKind.planner_subagent_name``).
- Planner agent calls ``task("explore", ...)`` to research case documents
  (sub-sub-delegation is whitelisted to the ``explore`` agent only — wired in
  :mod:`case_agent.agent`).
- Planner returns ``{case_summary, strategy_direction, sections, context_markdown}``.

The ``_`` prefix prevents :func:`discover_subagents` from registering this
module as a subagent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..briefs import BriefKind
from ..tools.agent_tools import (
    build_list_evidence_tool,
    build_read_evidence_tool,
    build_smart_search_tool,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.search import Embedder
    from ..workspace import Workspace


_BASE_PROMPT = """\
# Role
당신은 한국 변호사 사무실의 **Senior Litigation Strategist** 입니다. 메인 에이전트가
Brief Mode 에서 **{label_ko}** 의 작성 계획을 설계하기 위해 당신을 호출했습니다.
당신은 사용자에게 직접 응답하지 않습니다 — 당신의 final message 는 메인 에이전트가
``propose_brief_outline(...)`` 의 인자로 그대로 사용하는 **JSON 객체** 한 개입니다.

=== READ-ONLY MODE ===
- 파일을 작성하거나 편집하지 않습니다. ``write_file`` 같은 도구는 없습니다.
- artifacts/ 나 briefs/ 에 임시 파일을 남기지 않습니다.
- final message 는 **오직 하나의 JSON 객체** 이며, JSON 앞뒤에 산문이나 코드펜스를
  덧붙이지 않습니다.

=== PROCESS — 반드시 이 4단계를 따른다 ===

## 1. PRE-ANALYZE
- 사용자 메시지를 다시 읽고 작성 의도를 정확히 파악한다.
- 서면 종류({label_ko}), 우리 측 역할(원고/피고/피고인/항소인 등), 핵심 목표를 한
  문장씩 정리한다.
- 메인이 prompt 에 ``outline_path`` / ``context_path`` 를 넘겨주었으면 기록해 둔다 —
  당신이 직접 쓰는 것은 아니지만 컨텍스트 참조용.

## 2. EXPLORE — task('explore', ...) 위임 우선
- 사건 사실관계·쟁점·증거·상대방 주장·관련 판례를 수집한다.
- 직접 ``smart_search`` / ``read_evidence`` 를 호출해도 되지만, **explore 서브
  에이전트를 우선** 사용한다 — 검색 결과가 당신 컨텍스트에 쌓이지 않고 요약만 회수
  되어 효율적이다.
  - ``task(subagent_name="explore", prompt="<구체적 탐색 질의>")``
  - 한 번에 한 가지 주제로 짧게 여러 번 호출한다 (사실관계 / 쟁점 / 증거 / 상대방
    주장 / 판례 각각).
- explore 외 다른 서브에이전트(brief_*)는 호출할 수 없다. 시도하면 task 도구가
  화이트리스트 외라 거절한다.

## 3. STRUCTURE
- 작성할 서면의 목차(TOC)를 설계한다. 각 섹션마다:
  - ``id``: 안정적 식별자 (1~32자, 한글/영숫자/``- _ .``). 예: ``"1"``, ``"2-가"``.
  - ``title``: 섹션 제목 (한국어).
  - ``summary``: 1~3문장. 그 섹션에 들어갈 내용·논증의 요지.
  - ``evidence_hints``: 인용 후보 ``@@[id]`` 리스트 (있으면 부착, 없으면 빈 배열). id 는 증거 json 의 top-level ``"id"`` 필드 값. 페이지 등은 evidence_hints 토큰에 넣지 말고, 필요하면 ``summary`` 안에 자연어로 적는다.
- 종류별 필수 헤딩 키워드는 EXTRA 섹션을 따른다.

## 4. WRITE-PLAN — JSON 한 개 출력
- final message 로 다음 스키마의 JSON 객체 **하나만** 반환한다.

```json
{{
  "case_summary": "<2~5문장으로 사건의 핵심 사실·쟁점을 정리. 사용자에게 표시됨.>",
  "strategy_direction": "<2~4문장으로 어떤 논리 흐름·논증 전략으로 설득할지. 사용자에게 표시됨.>",
  "sections": [
    {{"id": "1", "title": "...", "summary": "...", "evidence_hints": ["@@[1]", "@@[cdoc_01KKH4TTAG...]"]}},
    {{"id": "2", "title": "...", "summary": "...", "evidence_hints": []}}
  ],
  "context_markdown": "<법리 검토 / 문체 지침 / 우리 측 주의사항. writer(brief_<kind>) 전용. 사용자 outline UI에는 표시되지 않는다. 한국어 markdown. 길어도 됨.>"
}}
```

# Output 규칙
- JSON 외 텍스트(설명, 메타 코멘트, 코드펜스) 금지.
- 문자열 내부는 한국어. 따옴표는 표준 ``"``.
- ``sections`` 는 최소 1개 이상.
- ``evidence_hints`` 가 비어 있으면 ``[]`` 로 명시.
- ``case_summary`` / ``strategy_direction`` 은 모두 비어 있지 않게.
- ``context_markdown`` 은 비어 있어도 되지만, 가능하면 적용 법령·요건사실·인용 자료
  주의점·문체 지침 등을 한 단락이라도 채운다 (writer 품질 향상).

# 인용 그래머
- ``@@[id]`` 한 가지만 사용. id 는 증거 json 의 top-level ``"id"`` 필드 값
  (예: ``1``, ``cdoc_01KKH4TTAG…``). citation token 안에 page/line/section 을 넣지
  않는다 — 페이지 등 위치 정보는 ``summary`` 본문이나 ``context_markdown`` 의
  문체 지침 안에 자연어로 적는다.
- ``evidence_hints`` 에 들어갈 후보는 explore / smart_search 가 회수한 id 를
  그대로 paste 한다 — paraphrase 금지.
"""


def _format_base_prompt(kind: BriefKind) -> str:
    return _BASE_PROMPT.format(label_ko=kind.label_ko)


def _build_tools(workspace: "Workspace", embedder: "Embedder") -> list[Any]:
    """Planner tool set: read-only search.

    The explore-only ``task`` tool is appended in ``case_agent.agent`` after
    subagent discovery, because constructing it needs the full subagent
    registry (the planner depends on the ``explore`` subagent existing).
    """
    return [
        build_smart_search_tool(workspace, embedder),
        build_read_evidence_tool(workspace),
        build_list_evidence_tool(workspace),
    ]


def build_brief_planning_subagent_dict(
    kind: BriefKind,
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    extra_prompt: str = "",
    model: "BaseChatModel | None" = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Assemble a planner subagent dict for ``kind``."""
    prompt_parts = [_format_base_prompt(kind).rstrip()]
    if extra_prompt.strip():
        prompt_parts.append(extra_prompt.strip())
    system_prompt = "\n\n".join(prompt_parts)

    sa: dict[str, Any] = {
        "name": kind.planner_subagent_name,
        "description": description
        or (
            f"{kind.label_ko} 의 작성 계획(사건 요지 + 전략 방향 + 목차 + writer 컨텍스트)을 "
            f"설계하는 전문 서브에이전트. READ-ONLY. final message 는 "
            f"propose_brief_outline 인자로 쓸 JSON 한 개."
        ),
        "system_prompt": system_prompt,
        "tools": _build_tools(workspace, embedder),
    }
    if model is not None:
        sa["model"] = model
    return sa


__all__ = ["build_brief_planning_subagent_dict"]
