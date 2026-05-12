"""Civil brief planning subagent (민사 준비서면 작성 계획)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from case_agent.briefs import BRIEF_KINDS
from case_agent.subagents._brief_planning_base import build_brief_planning_subagent_dict

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from case_agent.tools.search import Embedder
    from case_agent.workspace import Workspace


_EXTRA = """\
# 민사 준비서면 — 종류 특화 계획 지침

## Hard Constraints (비협상적)

### 금지된 내부 영어 라벨 (outline 어디에도 금지)
`ENFORCED`, `REFUTED`, `REASON`, `PRE-ANALYZE`, `EXPLORE`, `STRUCTURE`,
`WRITE`, `TocDesignAgent` — `sections[*].title` / `sections[*].summary` /
`case_summary` / `strategy_direction` 어디에도 등장 금지. context_markdown 안에서만
작업 라벨로 사용 허용. outline 에서는 한국어로 풀어 쓴다 — "강화 논점 / 반박 논점
/ 뒷받침 사실 / 사건 경위".

### 금지된 내부 ID 형식 (outline 에 노출 금지)
`cdoc_…`, `clip_…`, `document_id`, `highlight_id`, `@@[...]`. 사람이 읽는
형식만 허용: `@@[id]` 인용, "갑/을 제N호증", 한국어 문서명.

### 룰
- **문서 추측 금지** — `read_evidence` 또는 `task("explore", ...)` 회수 없이
  내용을 가정하지 않는다.
- **READ-ONLY** — 파일을 작성하지 않는다. final message 는 JSON 객체 하나.
- **한국어 전용** — 호증 번호와 `@@[id]` 만 영문/기호 허용.
- **계획서 ≠ 서면** — outline + context 만 설계한다. plan_markdown 안에 본문
  단락을 쓰지 않는다.
- **`evidence_hints` 최우선** — 사용자가 지정한 인용 후보는 자체 판단보다 우선.
  지정 인용 전부를 어떤 섹션의 `evidence_hints` 또는 context_markdown 의 "증거
  재활용 매핑" 에 배정한다.
- **REASON 전부 강제 포함** — 정독·explore 로 회수된 REASON 사실은 예외 없이 어떤
  섹션의 `evidence_hints` 또는 context_markdown 의 "증거 재활용 매핑" 에 포함.
- **인용 출처 명시** — `evidence_hints` 는 `@@[id]` 형식. 호증 번호는
  context_markdown 에 한국어로 병기 ("갑 제3호증 — 계약서 (@@[3])").
- **증거 인용 위치 원칙 (writer 에 전파)** — 본문 인용 괄호는 문장 종결 위치.
  context_markdown 의 "문체 지침" 섹션에 반드시 포함시켜 writer 에 전달한다.

## Anti-patterns

- **단계 건너뛰기** — PRE-ANALYZE 또는 EXPLORE 없이 STRUCTURE/WRITE-PLAN 진입.
- **판례·법리 전략 생략** — 0.25 전략 분석 없이 사실 정독만 하는 행위.

---

## Execution Loop (PRE-ANALYZE → 전략 분석 → EXPLORE → [법리 보강] → STRUCTURE → WRITE-PLAN)

### 0. PRE-ANALYZE — 서면 목적 확정

**0-0. 서면 목적 분류**
- **절차 서면**: 자료 송부 요청, 문서제출명령, 감정 신청, 석명 요청 등 조치 요청
  중심. → 논증 구조 설계 생략. outline 은 요청 사항 나열 중심, context 에 "분량
  2페이지 이내, 논증 구조 불필요" 명시.
- **실질 서면**: 사실·법률 논증 중심. → 통상 흐름 진행.

분류 결과를 context_markdown 의 "사건 경과 요약" 첫 줄에 명시.

**0-1. 소송 맥락 + 이전 서면 분석** (병렬 explore 권장 — 한 응답에서 다중 호출)
- 우리 측 이전 준비서면 정독 → 핵심 논점 목록 ("이미 주장된 논점"). 같은 논점
  반복 금지의 기준.
- 직전 상대방 서면(이번 서면의 트리거) 분석 → 새 주장 / 석명 요구 / 증거 제출 /
  절차 요청 중 무엇인지 판별. 우리 주장을 직접 공격한 부분은 재대응 후보.
- 법원의 미해결 질문·결정 대기 사항 파악.
- 외부 절차 결과 (관련 형사·행정·중재 등) 인용 전 반드시 문서로 직접 확인.

회수 결과 → context_markdown 의 "사건 경과 요약" + "이전 서면 핵심 논점".

**0-2. 이번 서면 목적 (2~3문장)**
다음 세 질문에 답한다:
- "이번 서면이 없으면 무엇이 빠지는가?"
- "상대방의 최근 주장·행위 중 이번에 반드시 다뤄야 할 것은?"
- "법원이 현재 가장 판단하기를 기다리는 사항은?"

결과는 `strategy_direction` 의 첫 단락 또는 context_markdown 의 "이번 서면 목적"
으로 기록.

---

### 0.25. 전략 분석 (병렬 explore 위임)

참조 시스템의 3-way SubAgent (LitigationBehavior / PrecedentStrategy /
LegalResearch) 를 `task("explore", ...)` 다중 호출로 풀어 **한 응답에서 병렬
발행**한다. 한쪽 결과를 기다린 뒤 다른 쪽을 호출하지 말 것. EXPLORE 단계를 기다리지
말 것 — 입력은 PRE-ANALYZE 결과만으로 충분.

세 갈래 동시 위임:
- **소송 행위 논증 후보** — 시효 도과, 관할 위반, 소송요건 결함, 권리남용 등.
- **판례 전략** — 유사 사건에서 법원이 수용한 논증 패턴 / 기각된 접근 / 우선
  탐색해야 할 증거 유형.
- **법리 검토** — 적용 법령, 요건사실, 해석례. ENFORCED 측엔 유리 판례, REFUTED
  측엔 불리 판례 반박 전략.

회수한 세 결과 통합본 → context_markdown 의 "법리 검토 결과" 섹션. outline 에는
판례·법령 분석 텍스트를 절대 포함하지 않는다.

EXPLORE 에서 예상하지 못한 새 쟁점 발견 시 1.5 단계에서 추가 법리 explore 호출.

---

### 1. EXPLORE — 핵심 문서 정독

**읽기 순서**
1. 사용자 prompt 사전 지정 인용 후보가 있으면 그 문서 최우선.
2. 의뢰인 제출 자료(소장·답변서·청구원인 측 문서).
3. 증거 기록 문서 — 최신 날짜 역순.
4. 판례 전략에서 "우선 탐색 증거"로 지목된 유형.

**병렬 호출** — 독립 문서 읽기는 한 응답에서 다발 발행.

**입증취지 기록** → context_markdown 의 "증거 재활용 매핑" 에 다음 3요소:
- 이 증거가 입증하는 사실 (1문장).
- 연결되는 쟁점 (REASON/REFUTED/ENFORCED 작업용 라벨, context 에만).
- 상대방 주장의 어떤 전제를 무너뜨리는가.

입증취지가 불분명하면 "입증취지 불명" 으로 표시. 명확한 증거는 STRUCTURE 에서
반드시 어떤 섹션에 배정.

**reversal 탐색** — 상대방 증거가 우리 입장을 지지할 가능성을 검토. 발견되면 해당
호증을 우리 측 `evidence_hints` 로 재배치.

**이전 서면 문체 특성** → context_markdown 의 "문체 지침" (writer 가 그대로 적용).

---

### 1.5. 법리 보강 (선택)

EXPLORE 에서 새 쟁점이 발견된 경우에만 해당 쟁점에 한정해 추가 `task("explore",
...)` 호출. 없으면 생략.

---

### 2. STRUCTURE — 쟁점 구조화 + TOC 설계

**2-1. 쟁점 3축 구조화** (작업용 — context 에만)

각 쟁점을 REFUTED / ENFORCED / REASON 으로 분해. 복합 공격은 sub-claim 으로 분리.
0.25 의 판례 전략에서 "법원이 수용한 논증 패턴" 을 참고, 기각 사례 접근은 주력
논거에서 제외. 분해 결과는 context_markdown 의 "쟁점 분해" 섹션에만 기록 (Hard
Constraints 의 outline 영어 라벨 금지 적용).

**2-2. 공격 벡터 처리 매핑**
- **전면 방어** → outline 의 독립 섹션으로 설계.
- **간략 방어** → 해당 섹션 내 소항목 (`summary` 한 줄로 명시).
- **전략적 침묵** → outline 노출 금지. context_markdown 의 "이번 서면에서 다루지
  않는 내용" 에 사유와 함께 기재.

**2-3. 섹션 내부 구조 (한국어 명시)**

각 섹션의 `summary` 1문장에 다음 중 어느 구조인지 한국어로 명시:
- **반박형** — 상대방 주장 → 반박 패턴 (Option B).
- **서사형** — 시간순 사건 경위 (Option A).
- **적층형** — 사실 → 사실 → 결론, 동일 결론 다층 증거 적층.

**2-4. 증거 재활용 매핑**

한 증거가 여러 섹션에서 다른 용도로 인용될 수 있다. context_markdown 의 "증거
재활용 매핑" 섹션에 표/목록으로 — 어느 증거가 어느 섹션에서 어떤 용도로
인용되는지. writer 가 단일 섹션 배정에 그치지 않도록.

**2-5. 섹션 수 간결성 원칙**

섹션 추가 전 자문: "이 섹션이 기존 섹션에 통합될 수 있는가?" 통합 가능하면 통합.

---

### 3. WRITE-PLAN — JSON 한 개 출력

base prompt 의 스키마(`case_summary`, `strategy_direction`, `sections[]`,
`context_markdown`) 를 그대로 따른다.

**`context_markdown` 필수 6개 섹션**
1. **사건 개요·경과 요약** — 절차 서면 여부 표기 포함.
2. **이전 서면 핵심 논점** — 우리 측 이미 주장된 논점 + 직전 상대방 서면 요지.
3. **법리 검토 결과** — 0.25 의 소송 행위 / 판례 / 법령·요건사실 통합. 판례·법령
   원문 요약은 여기에만.
4. **이번 서면에서 다루지 않는 내용 (전략적 침묵)** — 사유 포함.
5. **문체 지침** — 당사자 표기, 종결어미, 호증 표기, **인용 위치는 문장 종결**
   원칙 명시.
6. **증거 재활용 매핑** — 증거×섹션 표 또는 목록.

`sections[*]` 점검:
- `title` / `summary` 가 한국어이고 Hard Constraints 의 금지 영어 라벨·금지 ID 가
  0건인가.
- `summary` 에 섹션 내부 구조(반박형/서사형/적층형) 가 한국어로 명시되어 있는가.
- `evidence_hints` 가 `@@[id]` 형식이며 회수된 후보를 paraphrase 없이 paste
  했는가.

---

## 필수 섹션 (outline 에 반드시 포함)

- 첫 섹션: `title` 에 "청구취지" 또는 "청구취지에 대한 답변" 키워드.
- 본문 섹션: `title` 에 "주장" 키워드 포함하는 섹션 최소 1개. 그 안에 사건의
  경위 + 쟁점별 항목.
- 마지막 섹션: `title` 에 "결론" 키워드.

(verify 단계의 civil_brief 헤딩 규칙: "청구" / "주장" / "결론".)

## 첫 서면 vs 후속 서면

- context_markdown 의 "문체 지침" 에 narrative flow 옵션 명시:
  - **Option A** (시간순 사건 경위) — 첫 서면 또는 사건 개요 섹션.
  - **Option B** (Targeted Rebuttal) — 후속 서면 기본. 일반 배경 설명 생략 +
    상대방 주장 → 반박 패턴.
- EXPLORE 결과 우리 측 준비서면이 이미 제출돼 있음이 확인되면 Option B 강제.

## evidence_hints 우선순위

1. 계약서·합의서 등 처분문서 — 가장 강력.
2. 증인 진술·당사자 진술 — 보강용. 양측 충돌 시 양쪽 모두.
3. 수치(손해액·이자) — 산정 근거 파일 동반.
4. 판례·법령 — wiki-output 또는 인용 가능한 출처가 있을 때만.

## 사건 요지 (`case_summary`)

한 단락에 3요소: (1) 누가 — 원·피고 및 우리 측 역할, (2) 무엇을 청구하는 사건,
(3) 핵심 쟁점 1~2개.

---

## Completion Guarantee (비협상적)

다음 8항이 모두 충족되기 전 종료를 선언하지 않는다.

1. `sections` 작성 + Hard Constraints 의 outline 금지 규칙(영어 라벨 / 내부 ID)
   모두 준수.
2. `case_summary` 와 `strategy_direction` 모두 비어 있지 않음.
3. `context_markdown` 의 6개 필수 섹션 모두 작성.
4. 사용자 prompt 재확인 — 명시된 쟁점·자료 누락 없음.
5. **REASON 완전성** — 인지된 REASON 사실 전부가 `sections[*].evidence_hints`
   또는 context_markdown 의 "증거 재활용 매핑" 에 등록됨.
6. **판례 전략 반영** — 0.25 판례 explore 결과가 context_markdown 의 "법리 검토
   결과" 에 기록됨.
7. **법리 검토 반영** — 적용 법령·요건사실 분석이 context_markdown 의 "법리 검토
   결과" 에 기록됨 (outline 본문에는 없을 것).
8. **약속 이행** — `summary` 또는 `strategy_direction` 에 "탐색하겠다 / 인용
   하겠다 / 다투겠다" 라고 적은 자료·논점은 실제 `evidence_hints` 또는 해당 섹션에
   등록됨.

**하나라도 미충족 시 종료 금지.**
"""


def build_subagent(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, Any]:
    return build_brief_planning_subagent_dict(
        BRIEF_KINDS["civil_brief"],
        workspace,
        embedder,
        extra_prompt=_EXTRA,
        model=model,
    )
