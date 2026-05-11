---
name: brief_general
description: 민사 준비서면 이외의 모든 서면(답변서·항소이유서·보충서·의견서 등)을 단일 범용 페어(brief_planning_general + brief_general) 로 작성하는 흐름.
when_to_use: 사용자가 서면 작성을 요청했고 종류가 "민사 준비서면(civil_brief)" 이 아닌 경우. 종류 자체가 모호하더라도 범용 페어로 진입한다 — planner 가 사용자에게 직접 묻는다.
allowed-tools: enter_brief_mode, propose_brief_outline, approve_brief_outline, write_brief_section, exit_brief_mode, read_brief_mode, task, smart_search, list_evidence, read_evidence, read_file, verify_citations, check_completeness
argument-hint: [focus]
---

# 범용 서면 작성 (general_brief)

민사 준비서면 이외의 모든 서면은 이 단일 페어로 처리한다. planner 는 사용자에게
직접 질문하여 서면 종류·목적·우리 측 입장·핵심 쟁점·(선택) 인라인 템플릿을 수집한
뒤 outline 을 제안한다.

## 1. Brief Mode 진입
`enter_brief_mode(kind="general_brief")` 호출. 반환값에서 `outline_path`,
`output_path`, `context_path`, `task`, `version`, `planner_subagent_name`
(``brief_planning_general``), `writer_subagent_name` (``brief_general``) 확인.

## 2. Planner 위임 + 2-mode 응답 처리

`task(subagent_name="brief_planning_general", prompt=<사용자 원문 + outline_path +
context_path + (있으면) 이전 Q&A 누적>)` 호출.

planner 의 final message 는 **JSON 한 개**. 최상위 ``phase`` 키를 보고 분기:

### Mode A — `phase == "asking"`
```json
{"phase":"asking", "questions":["...", "..."]}
```
- ``questions`` 배열을 **사용자에게 그대로 출력**하고 **턴을 종료**한다. 다른 도구
  호출 금지.
- 사용자가 답변 메시지를 보내면, 메인이 이전 Q&A 와 새 답변을 prompt 에 누적해
  같은 planner 를 재호출한다 (1번으로 복귀하지 않고 같은 brief mode 세션 안에서).
- 한 번에 묻는 질문은 1~4개로 유지. planner 가 알아서 그렇게 설계되어 있다.

### Mode B — `phase == "ready"`
```json
{"phase":"ready", "case_summary":"...", "strategy_direction":"...",
 "sections":[...], "context_markdown":"..."}
```
- 3단계(propose_brief_outline) 로 진행.

## 3. 목차 제안 (`propose_brief_outline`)
planner 의 Mode B JSON 의 네 필드를 그대로 인자로 전달:
```
propose_brief_outline(
  sections=<planner.sections>,
  case_summary=<planner.case_summary>,
  strategy_direction=<planner.strategy_direction>,
  context_markdown=<planner.context_markdown>,
)
```
- outline 파일(`briefs/<task>_outline.md`): 사건 요지 + 전략 방향 + 목차 (사용자
  검토용).
- context 파일(`briefs/<task>_context.md`): 서면 종류·구조·문체·인라인 템플릿 등
  writer 가이드 (사용자에게는 표시되지 않음).
- phase → `awaiting_approval`.

## 4. 턴 종료 → 사용자 승인 UI 대기
`propose_brief_outline` 직후 **턴 종료**. UI 가 PlanApprovalPicker 표시.
- **Change** 피드백 → 2단계로 복귀 (planner 재호출, Mode B 결과로 outline 덮어쓰기).
- **Reject** → brief 모드 유지, 사용자 다음 지시 대기.
- **Accept** → 5단계.

## 5. 승인 + 섹션 단위 작성 루프
`approve_brief_outline()` 호출. todos 가 섹션별 자동 발행. 이후 모든 섹션 완료까지
반복:

1. `task(subagent_name="brief_general", prompt=<섹션 spec>)` 호출:
   ```
   [섹션 <N>/<Total>: <id>. <title>]
   요약: <summary>
   인용 후보: <evidence_hints>
   참고 outline: <outline_path>
   writer 컨텍스트: <context_path>   (서면 종류·문체·구조 — 반드시 먼저 읽을 것)
   출력 대상 파일: <output_path>  (직접 쓰지 말 것 — 메인이 append 한다)
   ```
2. `write_brief_section(section_id=<id>, content=<task return text>)` 호출.
3. `next_section` 이 있으면 1로 복귀. `all_done=True` 이면 6으로.

## 6. 종료 + 검증
`exit_brief_mode()` → `verify_citations(<output_path>)` 실패 0 →
`check_completeness("general_brief", <output_path>)` issues 빈 리스트 (min 인용 3개
규칙만).

## 7. 보고
사용자에게 한 단락으로: 작성한 서면 종류(planner 가 결정·기록), `briefs/general_brief_v<N>.md`,
섹션 N개, 인용 M개, 검증 결과.

## Rules
* 사용자가 명시적으로 "민사 준비서면" 을 요청하면 이 흐름이 아니라 `brief_draft`
  + `brief_planning_civil` 흐름을 사용한다.
* 종류 자체가 모호하면 `general_brief` 로 진입 — planner 가 사용자에게 직접 묻는다.
  메인 에이전트가 진입 전 종류를 다시 묻지 말 것.
* planner 응답이 ``phase=="asking"`` 이면 메인은 **추가 도구 호출 없이** 질문만
  사용자에게 출력하고 턴 종료. 사용자가 답변을 보내면 같은 planner 를 재호출.
* outline 은 메인이 직접 만들지 않는다 — 반드시 planner Mode B JSON 사용.
* 섹션 작성 prompt 에 `outline_path` / `context_path` / `output_path` 세 가지를
  모두 포함한다. writer 는 출력 파일에 직접 쓰지 않는다.
