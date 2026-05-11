---
name: brief_draft
description: Korean legal brief drafting entrypoint — Brief Mode 진입, 목차 제안, 사용자 승인, 섹션 단위 작성 루프.
when_to_use: 사용자가 민사 준비서면·답변서·항소이유서·의견서 등 정식 서면 작성을 요청했을 때.
allowed-tools: enter_brief_mode, propose_brief_outline, approve_brief_outline, write_brief_section, exit_brief_mode, read_brief_mode, task, smart_search, list_evidence, read_evidence, read_file, verify_citations, check_completeness
argument-hint: <kind> [focus]
---

# Brief Draft (서면 작성)

서면 작성은 **Brief Mode** 라는 별도 작동 모드를 통해서만 처리한다. 출력은 항상
`briefs/` 에 저장되며 Strategy Mode 와 동시 활성될 수 없다.

## Inputs

* `<kind>` — 서면 종류. 두 가지 중 하나:
  * `civil_brief` / `민사 준비서면` — 사용자가 **명시적으로** 민사 준비서면을 요청
    한 경우만. 전용 planner(`brief_planning_civil`) + writer(`brief_civil`) 사용.
  * `general_brief` / `범용 서면` — 그 외 모든 서면(답변서·항소이유서·의견서·
    보충서·반박서면 등)과 종류가 **모호한 경우 기본값**. 범용 planner
    (`brief_planning_general`) 가 사용자에게 직접 묻는 다중 턴 모드.
* `[focus]` — 선택. 서면의 주제·쟁점 키워드 (예: "이행지체 손해배상").

종류가 모호해도 사용자에게 다시 묻지 말고 `general_brief` 로 진입한다 — planner 가
대화로 종류를 결정한다.

## Steps

### 1. Brief Mode 진입
`enter_brief_mode(kind=<key 또는 라벨>)` 호출. 반환값에서 `outline_path`,
`output_path`, `context_path`, `task`, `version`, **`planner_subagent_name`**,
`writer_subagent_name` 을 받아둔다.

### 2. Planner 서브에이전트 위임 (목차 + 사건 요지 + 전략 + writer 컨텍스트 설계)
`task(subagent_name=<planner_subagent_name>, prompt=<사용자 원문 + outline_path +
context_path + (있으면) 이전 Q&A 누적>)` 호출. planner 는 READ-ONLY 로 동작하며
내부에서 필요한 만큼 `task("explore", ...)` 를 호출해 사건 자료를 수집한 뒤 JSON
한 개를 final message 로 반환한다 (메인이 직접 sections 를 만들지 말 것).

planner 응답의 최상위 `phase` 키로 분기:

#### Mode A — `phase == "asking"` (`brief_planning_general` 다중 턴 전용)
```json
{"phase": "asking", "questions": ["어떤 종류의 서면을 작성하실 건가요? …", "…"]}
```
- `questions` 배열을 **사용자에게 그대로 출력**하고 **턴을 종료**한다. 추가 도구
  호출 금지.
- 사용자 답변이 오면 이전 Q&A 와 새 답변을 누적한 prompt 로 같은 planner 를 재호출
  (2단계 반복). brief mode 세션은 유지 — `enter_brief_mode` 재호출 불필요.

#### Mode B — `phase == "ready"` 또는 phase 키 없음 (outline JSON)
```json
{
  "phase": "ready",
  "case_summary": "<2~5문장 사건 요지>",
  "strategy_direction": "<2~4문장 설득 논리 흐름>",
  "sections": [
    {"id": "1", "title": "청구취지", "summary": "...", "evidence_hints": ["@@[<소장 id>]"]}
  ],
  "context_markdown": "<법리 검토 / 문체 지침 / writer 주의사항>"
}
```
- 3단계(propose_brief_outline) 로 진행.
- `brief_planning_civil` 은 항상 이 단발 형식만 반환 (phase 키가 없을 수도 있음).
- `brief_planning_general` 은 정보가 충분히 모인 후 이 형식을 반환.

### 3. 목차 제안 (`propose_brief_outline`)
planner JSON 의 네 필드를 그대로 인자로 전달한다:

```
propose_brief_outline(
  sections=<planner.sections>,
  case_summary=<planner.case_summary>,
  strategy_direction=<planner.strategy_direction>,
  context_markdown=<planner.context_markdown>,
)
```

- outline 파일(`briefs/<task>_outline.md`) 에는 사건 요지 + 전략 방향 + 목차가 기록됨
  (사용자 검토용).
- writer 컨텍스트 파일(`briefs/<task>_context.md`) 에는 법리 검토·문체 지침이 기록됨
  (writer subagent 전용; 사용자에게는 표시되지 않음).
- phase 가 `awaiting_approval` 로 전환됨.

### 4. 턴 종료 → 사용자 승인 UI 대기
`propose_brief_outline` 호출 직후 **턴을 종료한다.** UI 가 PlanApprovalPicker
(Accept / Reject / Change) 를 표시한다. 사용자가 명시적 승인 메시지
("[사용자 승인됨] ...") 를 보내기 전에는 어떤 도구도 호출하지 않는다.

- **Change** 가 들어오면 (피드백 텍스트 포함) → 2단계로 복귀해 planner 를 다시 호출
  하고 `propose_brief_outline` 으로 outline / context 를 덮어쓴다.
- **Reject** 는 UI 가 닫힐 뿐 brief 모드는 유지 — 사용자의 다음 지시를 기다린다.
- **Accept** → 5단계로 진행.

### 5. Approve + 섹션 단위 작성 루프
승인 메시지를 받으면 `approve_brief_outline()` 호출. todos 가 섹션마다 한 항목씩
발행되고 (첫 항목 in_progress) 출력 파일이 헤더만으로 초기화된다.

이후 모든 섹션 완료까지 다음을 반복:

1. `task(subagent_name="brief_<kind>", prompt=<섹션 spec>)` 호출. prompt 형식:

   ```
   [섹션 <N>/<Total>: <id>. <title>]
   요약: <summary>
   인용 후보: <evidence_hints>
   참고 outline: <outline_path>
   writer 컨텍스트: <context_path>   (법리 검토 / 문체 지침 — 반드시 먼저 읽을 것)
   출력 대상 파일: <output_path>  (직접 쓰지 말 것 — 메인이 append 한다)
   ```

   subagent 는 context_path 를 먼저 읽고, 자료 탐색이 필요하면 explore 에 위임한 뒤,
   섹션 본문(헤딩 제외) 만 final message 로 반환한다.

2. `write_brief_section(section_id=<id>, content=<task return text>)` 호출.
   - `## <id>. <title>` 헤딩이 자동으로 부착되어 출력 파일에 append.
   - 해당 섹션 todo 가 completed, 다음 pending → in_progress 자동 갱신.
   - 응답의 `next_section` (또는 `all_done=True`) 확인.

3. `next_section` 이 있으면 1로 복귀. 없으면 6으로.

### 6. 종료
`exit_brief_mode()` 호출 → state.active=False.

이어서 출력 파일 전체에 대한 최종 검증:
- `verify_citations(<output_path>)` — 실패 0
- `check_completeness("<kind>", <output_path>)` — issues 빈 리스트

검증 실패 시:
- 해당 섹션을 식별 (어느 헤딩에 속한 인용/누락인지)
- 그 섹션을 다시 작성하기 위해 `write_brief_section` 만 다시 호출하면 append 가 추가
  되어 중복이 발생한다. 따라서 검증 실패 후 보강은 일반 `write_file` 로 출력 파일을
  수정하거나, 새 v(N+1) 로 다시 시작 (`enter_brief_mode` 재호출).

### 7. 보고

사용자에게 한 단락으로 보고:

```
{kind_label_ko} 초안을 `briefs/<kind>_v<N>.md` 에 작성했습니다. 섹션 N개,
인용 M개. verify_citations / check_completeness 통과. 추가 검토 필요 항목: ...
```

본문 전체를 chat 에 paste 하지 않는다.

## Rules

* 서면 작성은 **반드시 Brief Mode 를 통해서만** 진행한다. Strategy Mode 호출 금지.
* 산출 위치는 **반드시 `briefs/<kind>_v<N>.md`** (artifacts/ 가 아님). 도구가 자동
  결정하므로 직접 경로를 만들지 말 것.
* 사용자 승인 전 `approve_brief_outline()` 호출 금지.
* 섹션 작성 prompt 에 `outline_path` / `context_path` / `output_path` 세 가지 모두
  포함한다. subagent 는 출력 파일에 직접 쓰지 않는다 — 본문만 반환하고 메인이
  `write_brief_section` 으로 commit.
* outline / context 는 절대 메인이 직접 만들지 않는다. planner (`brief_planning_civil`
  또는 `brief_planning_general`) 가 JSON 으로 반환한 것을 그대로 사용한다.
* `brief_planning_general` 응답이 `phase=="asking"` 이면 메인은 추가 도구 호출 없이
  `questions` 만 사용자에게 출력하고 턴을 종료한다. 사용자 답변 후 같은 planner 를
  prompt 누적으로 재호출.
* 종류별 SKILL.md (`brief_civil` — 민사 준비서면, `brief_general` — 범용 서면) 에
  더 자세한 작성 룰이 있다 — outline 설계 + 섹션 위임 prompt 에 해당 룰 핵심을
  함께 전달하면 품질이 좋아진다.
