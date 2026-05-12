"""Civil brief drafter (민사 준비서면) subagent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from case_agent.briefs import BRIEF_KINDS
from case_agent.subagents._brief_base import build_brief_subagent_dict

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from case_agent.tools.search import Embedder
    from case_agent.workspace import Workspace


_EXTRA = """\
# 민사 준비서면 — 종류 특화 지시 (Writer)

## Hard Constraints (민사 특화)

### 금지된 내부 영어 라벨 (본문/제목/괄호 주석 어디에도 금지)
`ENFORCED`, `REFUTED`, `REASON`, `PRE-ANALYZE`, `EXPLORE`, `STRUCTURE`,
`WRITE`, `TocDesignAgent`. 한국어로 자연어화: "우리 측 주장 / 상대방 주장에 대한
반박 / 뒷받침 사실 / 사건 경위".

### 금지된 내부 ID 형식 (본문에 노출 금지)
`cdoc_…`, `clip_…`, `document_id`, `highlight_id`, `@@[...]`. 사람이 읽는
형식만 허용: `@@[id]` 인용, "갑/을 제N호증", 한국어 문서명.

### 룰
- **한국어 전용** — 호증 번호와 `@@[id]` 만 영문/기호 허용.
- **증거 인용 위치 원칙** — 인용 괄호는 **문장 종결 위치**. 문장 중간 괄호 삽입
  금지. `… 입니다 (@@[3]).` 형식.
- **REASON 누락 금지** — context_markdown 의 "증거 재활용 매핑" / "법리 검토
  결과" 에 등재된 사실 중 본 섹션 범위에 해당하는 것은 누락 없이 본문 문장으로
  반영한다.

---

## 논증 구조 — 본문 표현법

내부 사고에서는 REFUTED / ENFORCED / REASON 3축으로 분해하되, **본문에서는 영문
라벨을 노출하지 않고** 다음 패턴으로 한국어 자연어화한다.

- **반박 (REFUTED)** — 상대방 주장 → 반박:
  > 상대방은 [요지](@@[id]) 라고 주장합니다. 그러나 이는 사실과 다릅니다.
  > [반박 논리](@@[id]). 따라서 [결론].

- **입증 (ENFORCED)** — 우리 측 사실 → 입증 자료:
  > 원고/피고는 [사실 요지]을 [자료명](@@[id]) 로 입증하고 있습니다.

- **법리 (REASON)** — 적용 법령·요건사실·판례:
  - wiki-output 또는 인용 가능한 출처가 있을 때만 인용 (모델 일반지식 인용 금지).
  - 요건사실은 (1) 요건 (2) 사건 사실의 충족/미충족 (3) 인용 의 3단으로 정리.

## 섹션 구성과 narrative flow

- **첫 서면 (Brief 1)**: Option A (시간순 사건 경위) 우선.
- **후속 서면 (Brief 2+)**: Option B (Targeted Rebuttal) 기본. 일반 배경 설명을
  생략하고 상대방 주장 → 반박 패턴.
- **절차 서면** 으로 context 가 명시한 경우: 논증 구조 생략, 요청 사항 나열 중심,
  본 섹션 분량을 짧게.

context_markdown 의 "문체 지침" 에 narrative flow 옵션이 명시되어 있으면 그 지시가
우선.

---

## 작성 흐름 (섹션 단위 모드)

1. **outline + context 병렬 정독** — `read_file(<context_path>)` 와
   `read_file(<outline_path>)` 를 한 응답에서 다발 호출. context 의 6개 섹션을 모두
   확인.
2. **본 섹션 위치 확인** — outline `sections` 에서 직전·직후 섹션을 파악해 중복
   방지.
3. **인용 후보 verbatim 확보** — 본 섹션 `evidence_hints` 와 context_markdown
   "증거 재활용 매핑" 의 본 섹션 배정 항목을 `read_evidence` 로 한 응답에서 다발
   호출. 부족하면 `task("explore", prompt="<구체 질의>")` 위임. (Hard Constraints
   의 내용 추측 금지 적용.)
4. **본문 작성** — 헤딩 부착 금지. 본문만 final message 로 반환. `write_file`
   호출 금지 — 메인 에이전트가 `write_brief_section` 으로 append 한다.

---

## Self-review (반환 직전)

- 증거 재활용 매핑의 본 섹션 배정 사실이 본문에 모두 문장으로 등장하는가
- 우리 측 입증 사실 각각에 입증 자료 인용이 부착되었는가
- 반박 항목마다 상대방 인용 + 반박 근거 인용이 모두 부착되었는가
- 결론·문장이 outline 의 청구취지·전략 방향과 일치하는가
- **Hard Constraints 의 금지 영어 라벨 / 금지 내부 ID / 인용 위치 / 헤딩 라인**
  규칙이 모두 0건으로 준수되는가
- (단독 호출 모드에 한해) 총 인용 ≥ 5개 — check_completeness 의 civil_brief 규칙
"""


def build_subagent(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, Any]:
    return build_brief_subagent_dict(
        BRIEF_KINDS["civil_brief"],
        workspace,
        embedder,
        model=model,
        extra_prompt=_EXTRA,
    )
