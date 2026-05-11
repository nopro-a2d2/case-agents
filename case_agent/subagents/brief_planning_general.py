"""범용 서면 작성 planner subagent.

민사 준비서면 이외의 모든 서면 작성 계획을 단일 planner 가 담당한다. 기존 종류별
planner 와의 차이점은 **사용자와의 다중 턴 대화** 를 지원한다는 점이다:

- 호출 시점에 서면 종류·우리 측 입장·목적·핵심 쟁점·(선택) 인라인 템플릿이 사용자
  발화·이전 Q&A 만으로 결정되지 않으면, planner 는 final message 로
  ``{"phase":"asking", "questions":[...]}`` JSON 을 반환한다. 메인 에이전트는 이
  ``questions`` 를 사용자에게 그대로 보여주고 턴을 종료한다. 사용자 답변이 들어오면
  메인이 누적된 prompt 로 planner 를 재호출한다.
- 정보가 충분히 모이면 ``{"phase":"ready", "case_summary":..., ...}`` 의 outline
  JSON 을 반환한다. 메인은 이를 ``propose_brief_outline`` 에 그대로 전달한다.

기본 prompt 의 4단계(PRE-ANALYZE → EXPLORE → STRUCTURE → WRITE-PLAN) 와 단일 JSON
출력 규칙은 그대로 유지하되, EXTRA 가 2-mode 응답과 수집 정보 항목을 추가한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..briefs import BRIEF_KINDS
from ._brief_planning_base import build_brief_planning_subagent_dict

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.search import Embedder
    from ..workspace import Workspace


_EXTRA = """\
# 범용 서면 — 종류 특화 계획 지침 (Planner)

## 2-mode 응답 (필수)
이 planner 는 **두 가지 final message 형식 중 하나** 만 반환한다. 두 형식 모두 JSON
한 개. 앞뒤에 산문·코드펜스 금지.

### Mode A — 정보 수집 (asking)
서면 작성에 필요한 핵심 정보가 사용자 발화·이전 Q&A·자료 탐색만으로 결정되지 않은
경우. 메인 에이전트가 ``questions`` 를 사용자에게 그대로 표시하고 턴을 종료한다.

```json
{
  "phase": "asking",
  "questions": [
    "어떤 종류의 서면을 작성하실 건가요? (예: 답변서, 항소이유서, 보충서, 의견서 …)",
    "이 서면의 주된 목적은 무엇인가요? (예: 청구 기각 요청, 양형 자료 제출 …)"
  ]
}
```

### Mode B — 목차 제안 (ready)
정보가 충분히 모이면 기존 base prompt 의 outline 스키마를 그대로 사용하되,
최상위에 ``"phase": "ready"`` 를 추가한다.

```json
{
  "phase": "ready",
  "case_summary": "<2~5문장 사건 요지>",
  "strategy_direction": "<2~4문장 설득 논리 흐름>",
  "sections": [
    {"id": "1", "title": "...", "summary": "...", "evidence_hints": ["@@[...]"]}
  ],
  "context_markdown": "<서면 종류·문체·구조·인용 주의점 등 writer 가이드>"
}
```

## 수집할 정보 (Mode A 에서 묻는 항목)

1. **서면 종류** — 답변서·항소이유서·보충서·의견서·반박서면·기타. 어떤 명칭이어도
   허용. 종류가 결정되어야 writer 가 사용할 문체·구조를 context_markdown 에 적을 수
   있다.
2. **서면의 목적·결론** — 우리가 이 서면으로 도달하려는 결론 (청구 기각·감형·소
   각하·증거 신청 등).
3. **우리 측 입장** — 원고/피고/항소인/피항소인/피고인/변호인 등 절차상 지위.
4. **핵심 쟁점·주장** — 다투고자 하는 사실·법리. 상대방 주장이 있으면 함께.
5. **자료/증거 위치 또는 사건명** — 사건 자료가 워크스페이스 어디에 있는지(또는
   사건명·식별자) 가 모호하면 묻는다. 사건명이 사용자 발화에 있으면 묻지 말 것.
6. **(선택) 인라인 템플릿** — 사용자가 따라야 할 형식이나 예시가 있는지. 사용자가
   템플릿 본문을 prompt 에 붙여넣었으면 이 항목은 묻지 않는다.
7. **(선택) 문체·길이 선호** — 짧고 간결·격식 강조·요점 중심 등. 사용자가 명시한
   바 있으면 묻지 말 것.

## Mode A 운용 규칙
- 한 번에 묻는 질문은 **1~4개**. 핵심부터 묶어서 묻는다.
- 이미 사용자 발화·이전 Q&A 에 답이 있는 항목은 다시 묻지 않는다.
- ``smart_search`` / ``read_evidence`` / ``task("explore", ...)`` 로 답을 찾을 수
  있는 항목은 자료 탐색을 시도하고, 그래도 결정되지 않을 때만 묻는다.
- 사용자 발화에 인라인 템플릿이 들어 있으면 그 텍스트를 ``context_markdown`` 의
  "사용자 제공 템플릿" 항목으로 저장할 계획을 세운다 (실제 저장은 Mode B 응답에서).
- ``questions`` 배열 외 다른 키를 ``phase=="asking"`` 응답에 포함하지 않는다.

## Mode B 전환 조건
- 1~4 항목(종류·목적·우리 측 입장·핵심 쟁점) 이 모두 확정.
- 인용에 쓸 자료 위치(또는 사건 자료 디렉토리)가 명확하거나 ``explore`` 로 회수한
  evidence id 가 1개 이상.
- 위 조건이 모두 충족되면 즉시 Mode B 로 outline 제안. 모자라면 Mode A 로 추가 질문.

## context_markdown 구성 (Mode B)
범용 서면이므로 writer 에게 종류별 가이드를 명시적으로 전달한다:
1. **서면 종류 라벨** — 사용자가 결정한 명칭 (예: "항소이유서").
2. **우리 측 입장 및 결론** — 한 단락.
3. **구조 가이드** — 서면 종류에 적합한 헤딩/논증 순서. 예시: 항소이유서면 "원심
   판단 → 부당성 → 정당한 판단" 의 3단 구조.
4. **인용 자료 주의점** — 인용 후보 id 와 사용 위치, 처분문서·진술 충돌 시 양측 인용.
5. **(있으면) 사용자 제공 템플릿** — 인라인 텍스트 그대로 paste.
6. **문체·길이 지침** — 사용자 선호 또는 종류 관례.

## 사건 요지 작성 (Mode B)
``case_summary`` 는: 1. 사건 식별(당사자/사건명/단계), 2. 작성 사유, 3. 다투는 핵심.

## evidence_hints 우선순위 (Mode B)
- 핵심 쟁점 입증·반박 자료 각각에 ``@@[<id>]`` 후보 1개 이상.
- 상대방 주장이 있으면 그 출처(공소장·소장·준비서면 등) 인용 후보를 우선 부착.
- evidence_hints 는 explore / smart_search 가 회수한 id 를 paraphrase 없이 그대로
  paste — 위조 금지.
"""


def build_subagent(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, Any]:
    return build_brief_planning_subagent_dict(
        BRIEF_KINDS["general_brief"],
        workspace,
        embedder,
        extra_prompt=_EXTRA,
        model=model,
    )
