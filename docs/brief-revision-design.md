# Brief Revision Feature — End-to-End Design

## Context

현재 시스템은 서면을 **새로 작성**(plan → write)하는 흐름만 지원합니다. 사용자가 1차 초안을 받은 뒤 "이 부분만 더 강하게", "여기 표현 바꿔줘" 같은 **수정 요청을 자연스럽게 하는 채널**이 없습니다. 그래서 사용자는 외부 도구로 직접 편집하거나 처음부터 다시 생성을 돌려야 합니다.

목표: 사용자가 서면 에디터 옆 채팅 패널에서 (a) 자유 채팅으로, 또는 (b) 본문의 일부를 드래그 선택해 첨부한 뒤 수정 요청을 보내면, 에이전트가 부분 수정한 새 버전(`<kind>_vN+1.md`)을 만들어내고 결과가 에디터에 반영되는 흐름.

세 프로젝트(`evidence-frontend`, `legal-backend`, `case-agents`)에 걸친 변경이라 **통신 프로토콜이 가장 중요한 설계**입니다.

## Confirmed Design Decisions (user)

1. 통신 채널: **WebSocket 스트리밍을 end-to-end**로 (frontend ↔ backend ↔ case-agents)
2. 선택 단위: **TinyMCE 문자 offset + 선택 텍스트** (start/end + selected_text)
3. 버전 정책: **새 버전 파일** `briefs/<kind>_v{N+1}.md` 생성 (in-place 갱신 금지)
4. UI 위치: **서면 에디터 옆 전용 수정 채팅 패널** 신설

## High-Level Architecture

```
┌─────────────────────────────────────┐
│ evidence-frontend                   │
│  - TinyMCE editor (selection capture)│
│  - <BriefRevisionChatPanel> (new)   │
│  - useRevisionSocket() hook (new)   │
└────────────┬────────────────────────┘
             │ WS /writing-request/:id/revise/ws
             │ frame: {prompt, attachments?, action?}
             │ events: token, tool_start, tool_end, done(new_version)
             ▼
┌─────────────────────────────────────┐
│ legal-backend (Express)             │
│  - WS proxy: /writing-request/      │
│      :id/revise/ws  (new)           │
│  - Auth (JWT), session binding      │
│  - On done(new_version): fetch md   │
│    from case-agents, push to S3,    │
│    update WritingRequest entity     │
└────────────┬────────────────────────┘
             │ WS /ws  (existing case-agents endpoint)
             │ +new frame fields: attachments, mode_hint
             ▼
┌─────────────────────────────────────┐
│ case-agents (FastAPI + LangChain)   │
│  - ws_server.py: extend frame parser│
│  - brief_mode.py: add `revising`    │
│    phase + replace_section          │
│  - new tool: revise_brief_section   │
│  - new subagent: brief_revise_<kind>│
└─────────────────────────────────────┘
```

## Wire Protocol (WebSocket frame schema)

### Client → Server (frontend → backend → case-agents)

```jsonc
{
  "prompt": "이 부분 표현을 더 단호하게 바꿔줘",
  "writing_request_id": "wreq_01HXY...",    // backend uses for session bind
  "action": "revise",                       // "revise" | "chat" (free chat in revision)
  "attachments": [
    {
      "type": "brief_selection",
      "section_id": "2",                    // resolved by frontend from offset (best-effort)
      "start": 1234,                        // TinyMCE char offset in section
      "end": 1380,
      "text": "선택된 본문 ..."
    }
  ]
}
```
- `attachments`가 비어있으면 free-form 수정 채팅.
- `section_id`는 frontend에서 추정해서 보내지만 case-agents에서도 `selected_text`를 가지고 검증/보정.
- 기존 `{"prompt": "..."}` 프레임과 100% 하위호환(`attachments` optional).

### Server → Client (streaming events)

기존 `headless._serialize` 스키마 그대로 재사용 + 하나만 추가:

```jsonc
{ "type": "brief_revision_done",
  "old_version": 3,
  "new_version": 4,
  "output_path": "briefs/civil_brief_v4.md",
  "changed_section_ids": ["2"] }
```

이 이벤트는 `revise_brief_section` tool의 종료 시점에 case-agents가 emit. 기존 `done` 이벤트는 turn 종료용으로 그대로 유지.

## case-agents 변경

### A. `brief_mode.py` — `revising` phase 추가

`BriefModeState.phase`에 `"revising"` 추가. 전이:
```
done ──[start_revision]──▶ revising ──[finalize_revision]──▶ done(v+1)
drafting ──[start_revision]──▶ revising (drafting 중에도 가능)
```

새 헬퍼:
- `start_revision(workspace) -> BriefModeState`
  - 현재 active state에서 `version+1`로 새 version 할당
  - `output_path`를 `briefs/<kind>_v{N+1}.md`로 갱신
  - 기존 v{N} 파일 내용을 baseline으로 새 파일에 복사 (섹션 구조 유지)
  - sections의 `completed` flag는 모두 True 유지 (이미 작성된 상태)
  - `phase="revising"`로 설정
- `replace_section(workspace, section_id, new_content) -> BriefModeState`
  - `phase=="revising"`만 허용
  - output_path 파일에서 `## <id>. <title>` 블록만 정확히 찾아 교체 (regex)
  - 다른 섹션은 건드리지 않음
- `finalize_revision(workspace) -> BriefModeState`
  - `phase="done"`으로 되돌리고, `active=False`
  - 차후 또 수정하면 다시 `start_revision`이 v+2 만듦

핵심 파일: `case_agent/loop/brief_mode.py`. 기존 `propose_outline`, `approve_outline`, `append_section`은 손대지 않음.

### B. 새 tool: `revise_brief_section`

`case_agent/tools/brief.py`에 추가. 시그니처:

```python
@tool
async def revise_brief_section(
    section_id: str,
    instruction: str,
    selection_text: str = "",
    selection_offsets: dict | None = None,  # {"start": int, "end": int}
) -> dict:
    """phase=drafting|done 이면 start_revision을 자동 호출.
    그 다음 subagent `brief_revise_<kind>`에게 위임:
      - 입력: 현재 섹션 본문 + selection + instruction + outline/context 경로
      - 출력: 교체할 섹션 본문 markdown
    그리고 replace_section으로 파일 수정 + brief_revision_done 이벤트 emit.
    """
```

반환값:
```python
{"status": "ok", "section_id": "...", "new_version": N+1,
 "output_path": "briefs/...", "diff_preview": "..."}
```

### C. 새 subagent: `brief_revise_<kind>`

`case_agent/subagents/brief_revise.py` (4종: civil/defense/appeal/answer). `_brief_base.py`를 그대로 상속.

System prompt 요점:
- 입력에 `<current_section>`, `<selection>` (있으면), `<instruction>`이 들어있음
- selection이 있으면 그 범위만 surgical하게 고침. 없으면 instruction을 섹션 전체에 적용
- 인용 형식(`path#anchor`)과 어조는 그대로 유지
- 출력은 **섹션 본문 markdown 전체** (한 섹션을 통째로 교체할 수 있도록)
- `write_brief_section` 같은 mutation tool은 호출 금지 — 텍스트만 반환

### D. `ws_server.py` 프레임 파서 확장

`run_turn` 직전에 `attachments`를 prompt에 인라인:

```python
attachments = payload.get("attachments") or []
if attachments:
    prompt = _wrap_with_attachments(prompt, attachments)
```

`_wrap_with_attachments`는 attachments를 XML-ish 태그로 prompt 본문 앞에 prepend (LLM이 자연어로 인식):

```
<user-message>이 부분 표현을 단호하게 바꿔줘</user-message>
<brief-selection section_id="2" start="1234" end="1380">
선택된 본문 ...
</brief-selection>
```

또한 `action="revise"`이면 시스템 reminder를 추가해서 메인 에이전트가 `revise_brief_section` tool을 우선 호출하도록 유도. `force_brief`와 유사하게 `force_revise` 플래그를 `stream_query`에 전달.

핵심 파일: `case_agent/loop/ws_server.py`, `case_agent/loop/runner.py`, `case_agent/loop/query.py`(force flag 처리), `case_agent/prompts/main_system.md`(revise tool 호출 지시 추가).

### E. 이벤트 직렬화

`case_agent/loop/types.py`에 `BriefRevisionDone` event dataclass 추가. `headless._serialize`에 분기 추가. tool 내부에서 streaming events queue로 emit.

### F. 테스트

- `tests/test_brief_revision_mode.py`: start_revision → replace_section → finalize 사이클, v+1 파일 존재 확인
- `tests/test_revise_tool.py`: tool wrapper가 subagent를 호출하고 파일을 교체하는지 (subagent는 mock)
- `tests/test_ws_attachments.py`: attachments가 있는 프레임이 prompt에 인라인되는지

## legal-backend 변경

### A. 새 WebSocket 라우트

`src/modules/writing-request/writing-request.ws.ts` 신설.

- 경로: `WS /api/v1/writing-request/:id/revise/ws`
- 미들웨어: JWT 인증 (기존 `authMiddleware`), `:id` ownership 검증
- 연결 즉시 case-agents `/ws`로 outbound WS 오픈 (ws 라이브러리 또는 native)
- case-agents URL은 `config.A2D2_WS_URL`(신규 env). 단일 case-agents 프로세스가 멀티 케이스를 다루지 못한다면 backend가 case별 process pool 관리 — 현재 ws_server는 process당 1 case에 묶임을 감안해 **case-agents 측 멀티-case ws 지원이 prerequisite**(아래 Open Question 1).

### B. 메시지 프록시 & S3 sync

- 클라이언트 → 케이스 에이전트: 프레임에 `case_id`, `writing_request_id`를 강제로 주입 후 forward
- 케이스 에이전트 → 클라이언트: 그대로 forward, 다만 `brief_revision_done` 이벤트 도착 시:
  1. case-agents의 새 `output_path`를 fetch (현재 backend가 case-agents 파일을 가져오는 방식 — Open Question 2. 콜백 패턴에서 쓰던 artifact endpoint 재사용 또는 신규 endpoint)
  2. markdown → HTML 변환 (또는 markdown 그대로 저장)
  3. S3에 `case/{case_id}/brief/{job_id}/v{N+1}.md` 업로드
  4. WritingRequest entity의 `current_version`, `versions[]` 갱신
  5. 클라이언트에 `brief_revision_persisted` 이벤트 추가 emit (FE가 React Query invalidate에 사용)

### C. 엔티티 확장

`writing-request.entity.ts`:
```ts
versions: Array<{
  version: number;
  output_s3_key: string;
  created_at: Date;
  source: "plan" | "write" | "revise";
  changed_section_ids?: string[];
}>;
current_version: number;
```
기존 단일 `write_content_s3_key`는 호환을 위해 유지하되 `versions[current_version-1]`을 가리키게.

### D. 기존 REST 엔드포인트 보완

폴백/조회용:
- `GET /writing-request/:id/versions` — 버전 목록
- `GET /writing-request/:id/versions/:n` — 특정 버전 HTML/MD

핵심 파일: `src/modules/writing-request/writing-request.routes.ts`, `writing-request.controller.ts`, `writing-request.service.ts`, `writing-request.entity.ts`, 신규 `writing-request.ws.ts`.

## evidence-frontend 변경

### A. 새 컴포넌트: `<BriefRevisionChatPanel>`

위치: `src/components/case-evidence/case-detail-list/writing-request/revision-chat/`

- `document-editor-wrapper.tsx`의 우측 또는 하단에 dock
- 구성:
  - 메시지 리스트 (streaming text, tool activity bubbles)
  - 입력창 + "선택 첨부" 칩 (현재 캡처된 selection 미리보기 + 제거 버튼)
  - 전송 버튼

### B. 선택 캡처 훅: `useEditorSelection`

위치: `.../revision-chat/use-editor-selection.ts`

- 기존 TinyMCE selection 추적 코드(`case-document-editor-ckeditor.tsx`의 selectionchange 핸들러) 재사용
- 노출: `{ start, end, text, sectionId }` (sectionId는 본문에서 `## N. title` 헤더를 역추적해 추정)
- "이 선택을 채팅에 첨부" 액션 → panel의 입력 컨텍스트에 주입 (Jotai atom: `selectedRevisionRangeAtom`)

### C. WS 클라이언트 훅: `useRevisionSocket`

위치: `.../revision-chat/use-revision-socket.ts`

- `useEffect`로 WS connect on mount
- 메시지 수신 → reducer가 token/tool_start/tool_end/brief_revision_done/error 누적
- 송신: `send({prompt, attachments, action: "revise"})`
- `brief_revision_persisted` 수신 시 React Query `writing-request/:id` invalidate → 에디터 새 버전 fetch & 로드
- 재연결 로직 (지수 백오프)

### D. 플로팅 셀렉션 툴바 (선택사항, 빠른 진입)

선택 시 작은 툴바 "이 부분 수정 요청" 버튼 → 채팅 패널 입력에 selection 첨부 + focus.

### E. 타입

`src/apis/type/case-type/revision-type.ts`:

```ts
export type BriefSelectionAttachment = {
  type: "brief_selection";
  section_id: string;
  start: number;
  end: number;
  text: string;
};
export type RevisionWSEvent =
  | { type: "token"; text: string }
  | { type: "tool_start"; ... }
  | { type: "tool_end"; ... }
  | { type: "brief_revision_done"; old_version: number; new_version: number; output_path: string; changed_section_ids: string[] }
  | { type: "brief_revision_persisted"; new_version: number; s3_key: string }
  | { type: "done"; reason: string };
```

핵심 파일: 신규 `revision-chat/` 디렉토리, `document-editor-wrapper.tsx`(panel 마운트), `apis/type/case-type/revision-type.ts`, env (.env에 `VITE_WS_URL`).

## Critical Files (touchpoints summary)

**case-agents**
- `case_agent/loop/brief_mode.py` — `revising` phase, `start_revision`/`replace_section`/`finalize_revision`
- `case_agent/tools/brief.py` — `revise_brief_section` tool
- `case_agent/subagents/brief_revise.py` — 4 kind subagents (NEW)
- `case_agent/loop/ws_server.py` — frame attachments parsing
- `case_agent/loop/runner.py`, `query.py` — `force_revise` flag wiring
- `case_agent/loop/types.py`, `headless.py` — `BriefRevisionDone` event
- `case_agent/prompts/main_system.md` — revise tool 사용 지침

**legal-backend**
- `src/modules/writing-request/writing-request.ws.ts` (NEW)
- `src/modules/writing-request/writing-request.routes.ts` — WS 등록, versions REST
- `src/modules/writing-request/writing-request.entity.ts` — versions[] 필드
- `src/modules/writing-request/writing-request.service.ts` — S3 sync 로직
- `src/config/index.ts` — `A2D2_WS_URL` env

**evidence-frontend**
- `src/components/case-evidence/case-detail-list/writing-request/revision-chat/` (NEW dir)
- `src/components/case-evidence/case-detail-list/writing-request/document-editor/components/wrapper/document-editor-wrapper.tsx` — panel mount
- `src/apis/type/case-type/revision-type.ts` (NEW)
- `.env` — `VITE_REVISION_WS_URL`

## Reuse Inventory

- **case-agents**: `brief_mode` state machine, `_brief_base.py` subagent, `briefs_output_path` 헬퍼, `_VERSION_RE`, `find_section`, `workspace.glob`
- **legal-backend**: `authMiddleware`, `S3Client` wrapper, WritingRequest state machine, 기존 콜백 핸들러 패턴 (구조 차용)
- **frontend**: 기존 TinyMCE selection 추적, Jotai atom 패턴, React Query, `ClientMessageComposer`의 파일 첨부 UI (참고용)

## Verification Plan

### Unit
```bash
# case-agents
cd /data/nopro/case-agents && pytest tests/test_brief_revision_mode.py tests/test_revise_tool.py tests/test_ws_attachments.py -v
ruff check case_agent/
```

### Integration (case-agents 단독)
1. fixture로 v1 brief 만들어둠
2. `headless.py`에 `{"prompt": "...", "attachments": [...], "action": "revise"}` JSON 라인 입력
3. stdout NDJSON에서 `brief_revision_done` + `done` 이벤트 확인
4. `briefs/<kind>_v2.md` 파일 존재 및 해당 섹션만 바뀐 것 검증

### End-to-end (3-tier)
1. case-agents WS 서버 띄움 (`python -m case_agent web --case=<id> --root=<workspace>`)
2. legal-backend 띄움 (`A2D2_WS_URL`을 위 서버로)
3. evidence-frontend dev server (`npm run dev`)
4. 브라우저에서:
   - 기존 v1 브리프 로드
   - 본문 일부 드래그 → 툴바 "수정 요청" 클릭
   - 패널에서 "이 부분을 단호하게" 전송
   - 스트리밍 토큰 표시, tool 활동 표시, `brief_revision_done` 이벤트 도착
   - 에디터가 자동으로 v2로 갱신, 해당 섹션만 바뀐 것 시각적 확인
   - DB에서 WritingRequest.versions에 v2 row, S3에 새 키 확인

### 회귀
- 기존 plan/write 흐름은 그대로 동작 (`tests/test_brief_mode.py`, 기존 백엔드 callback 테스트 통과)

## Open Questions / Risks

1. **case-agents 멀티 케이스 WS**: 현재 `ws_server.create_app(case, root)`는 프로세스당 1 case에 고정. 프로덕션에서 다수 케이스를 다루려면 (a) backend가 case별 case-agents 프로세스 풀을 관리하거나 (b) ws_server를 멀티-case로 리팩터링 필요. 본 플랜은 (a)를 가정하고 backend WS 라우트에서 케이스별 connection 관리 — 실제 배포 환경 확인 필요.
2. **case-agents 파일 read API**: backend가 `briefs/<kind>_v{N+1}.md`를 가져오는 방식. 현재 콜백 패턴이 어떻게 가져오는지 추가 확인이 필요(공유 볼륨? HTTP fetch?). WS 이벤트 페이로드에 파일 본문 자체를 inline해도 됨(가장 단순).
3. **selection offset 안정성**: TinyMCE iframe 내 HTML offset과 case-agents 측 markdown offset이 다름. `selected_text` 스니펫을 fuzzy-match로 markdown 본문에서 찾는 게 더 robust — section_id + selected_text 조합으로 위치 잡고 offset은 hint로만 사용 (이 플랜이 채택한 방식).
4. **동시 수정 충돌**: 사용자가 v2 수정 중에 또 수정 보내면? → ws_server가 "turn in progress" 거부하는 기존 동작 유지. UI에서 비활성 처리.

## Suggested Implementation Order

1. **case-agents**: brief_mode 확장 + replace_section + 테스트 (가장 격리됨)
2. **case-agents**: revise tool + subagent + ws frame attachments + e2e headless 테스트
3. **legal-backend**: WS proxy + entity versions[] + S3 sync (case-agents 모킹으로 단위 테스트)
4. **evidence-frontend**: 타입 + WS 훅 + 패널 컴포넌트 + 통합 (기존 selection 코드 재사용)
5. 3-tier 통합 테스트
