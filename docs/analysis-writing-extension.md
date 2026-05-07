# Case-Agent 확장: 자료 분석 & 서면 작성

> **작성일**: 2026-05-06  
> **연구 방법**: 코드베이스 탐색 + Codex 컨설팅 (61,759 토큰)  
> **상태**: 방향성 문서 (미구현)

---

## 배경

현재 case-agent는 법률 문서 **QA**에 최적화되어 있다.

```
사용자 질의 → smart_search → read_with_anchor(4KB) → 인용 답변
```

1~3턴 안에 처리하며, 벤치마크(`benchmark_indictment.json`)에서 검증된 구조다.

문제는 **자료 분석**과 **서면 작성**은 QA와 근본적으로 다른 요구사항을 가진다는 것이다.

---

## 현재 아키텍처 분석

### 에이전트 루프 (`case_agent/loop/query.py`)

- 최대 25턴 hand-rolled async 루프
- 각 턴: 모델 스트리밍 → tool_calls 있으면 실행 → ToolMessage 추가 → 다음 턴
- 전체 메시지 히스토리를 상태로 유지 (컨텍스트 오염 위험)
- 체크포인트 없음 → 대형 작업 중단 불가

### 현재 도구

| 도구 | 역할 | QA 적합성 | 분석/서면 적합성 |
|------|------|-----------|----------------|
| `smart_search(query, k=8)` | 시맨틱 검색 + 1-hop KG 확장 | ✅ 강함 | ⚠️ 반복 검색 비용 |
| `read_with_anchor(citation, 4KB)` | 청크 읽기 | ✅ 충분 | ❌ 50페이지 = 50+ 호출 |
| `list_evidence(person, category)` | 소스 열거 | ✅ | ✅ |
| `verify_citations(path)` | 인용 문법 검증 | ✅ | ⚠️ 문법만, 논거 검증 아님 |
| `check_completeness(kind, path)` | 서면 구조 체크리스트 | — | ✅ 하지만 사후 검증만 |

### Sub-agent 위임

- `task(subagent_name="explore", prompt)` → Gemini Flash + 읽기 전용 도구
- 출력: JSON `{summary, citations, search_trace}` 단일 블롭
- **문제**: 대형 수집은 불투명하고 비용이 크며 재사용 불가

---

## 핵심 진단

> **Codex**: "QA와 합성(synthesis)은 같은 루프에서 돌아가는 것이 아니다. 아키텍처 자체를 분리해야 한다."

| 차원 | 현재 (QA) | 분석/서면에 필요한 것 |
|------|-----------|---------------------|
| 수집 | 쿼리별 smart_search | 문서 전체 인덱싱 + 청크 배치 읽기 |
| 청킹 | 4KB read_with_anchor | 페이지 범위, 슬라이딩 윈도우 |
| 합성 | 도구 피드백 per turn | 수집 완료 후 별도 작성 단계 |
| 초안 | 단일 아티팩트 버전 | 단계별: 개요 → 초안 → 검토 → 최종 |
| 검증 | 인용 문법만 | 주장 지원 검증, 교차 문서 일관성 |
| 상태 | 전체 메시지 히스토리 | 파일 기반 중간 아티팩트 |

---

## 권고 아키텍처: Evidence Pack 중심

### 두 경로 분리

```
QA 경로 (기존 유지, 변경 없음)
  사용자 질의 → smart_search → read_with_anchor → 인용 답변

합성 경로 (신규)
  Planner
    → Gather Workers (증거 수집)
    → Synthesizer (초안 작성)
    → Verifier (논거 검증)
    → Finalizer (최종 서면)
```

### 파일 기반 중간 아티팩트

채팅 히스토리를 상태로 쓰지 않는다. 모든 상태는 파일이다.

```
artifacts/{task_id}/
  document_map.json         # 문서 구조 인덱스 (목차)
  evidence.jsonl            # 수집된 증거 행들
  outline.json              # 섹션 구조 계획
  claim_table.json          # 초안에서 추출된 주장 목록
  draft.md                  # 현재 초안
  verification_report.json  # 검증 결과
```

**evidence.jsonl 행 스키마:**
```json
{
  "fact": "피고인은 2023년 3월 5일 현금을 수수했다",
  "category": "범행일시",
  "entity": "피고인 홍길동",
  "citation": "sources/indictment.json#p3",
  "quote": "2023. 3. 5. 현금 500만 원을 수수하였다",
  "confidence": 0.95
}
```

---

## 자료 분석 확장

### 신규 도구 (우선순위 순)

**1. `map_document(path)` — 최우선**

문서를 읽기 전에 구조를 파악한다. 맹목적 순차 읽기 대신 선택적 읽기를 가능하게 한다.

```python
# 반환 예시
{
  "pages": 52,
  "sections": ["공소사실", "증거목록", "법령적용"],
  "parties": ["검사", "피고인 홍길동"],
  "anchors": ["p1", "p2", ..., "sec:공소사실"],
  "chunk_ids": [...]
}
```

**2. `bulk_read(citations: list[str])` — 두 번째**

여러 앵커를 한 번에 읽어 `{citation: snippet}` 반환.  
50페이지 문서의 50+ tool call 문제를 해결하는 핵심 도구.  
기존 `read_with_anchor`의 배치 래퍼.

**3. `extract_to_evidence(scope, instructions, output_path)` — 세 번째**

텍스트 읽기 → 증거 구축으로의 전환점.  
여러 청크에서 스키마 기반으로 추출해 `evidence.jsonl`에 append.  
서브에이전트가 JSON 블롭을 반환하는 대신 파일에 누적.

### 프롬프트 변경

현재 Gather → Action → Verify 루프에 **분석 모드** 추가:

```
[분석 모드 규칙]
1. map_document로 시작 — 읽기 전 구조 파악 필수
2. bulk_read로 관련 섹션 수집
3. extract_to_evidence로 증거 행 누적
4. evidence.jsonl 완성 전 초안 작성 금지
5. 모든 추출 행은 인용 출처(citation) 필수
```

### 루프 변경

- 분석 모드에 한해 턴 예산 증가: 25 → 50
- 페이즈 간 체크포인트 추가 (Map → Extract → Verify)
- QA 경로는 변경 없음

---

## 서면 작성 확장

### 신규 도구

**4. `create_outline(kind, issue, evidence_path)`**

`check_completeness`의 역방향: 체크가 아니라 생성.

```python
# kind 예시: "민사준비서면", "증거인부서", "증인심문사항"
# 출력: outline.json
{
  "sections": [
    {"id": "1", "title": "청구취지", "required": true, "evidence_filter": "category:청구"},
    {"id": "2", "title": "청구원인", "required": true, "evidence_filter": "category:사실관계"},
    ...
  ]
}
```

**5. `write_section(section_id, outline_path, evidence_path)`**

전체 서면을 한 번에 생성하지 않는다. 섹션 단위로 작성 → 검증 → 다음 섹션.  
입력: outline + 해당 섹션 필터된 증거 (전체 히스토리 아님).

**6. `verify_claim_support(draft_path, evidence_path)`**

현재 `verify_citations`(문법 검증)를 논거 검증으로 강화.

검출 항목:
- 인용 없는 사실 주장
- 주장을 뒷받침하지 않는 인용
- 날짜/당사자 불일치
- 반대 증거 미언급
- 과장 주장 (overclaim)

### 프롬프트 변경

서면 작성 모드:

```
[서면 작성 모드 규칙]
1. create_outline으로 섹션 구조 먼저 생성
2. 내부 outline 검토 후 작성 시작
3. write_section: 한 섹션씩 작성
4. 각 섹션 완료 후 verify_claim_support 실행
5. 검증 통과 후 다음 섹션
6. 전체 서면 한 번에 생성 금지
```

---

## Anti-patterns (Codex 권고)

하지 말아야 할 것들:

1. **`max_turns`를 25→100으로 올리고 해결됐다고 하지 않는다**  
   → 턴 수가 아니라 아키텍처 문제다

2. **전체 문서를 raw text로 컨텍스트에 덤프하는 도구를 만들지 않는다**  
   → map_document → bulk_read 선택적 읽기를 사용

3. **모든 작업에 무거운 합성 워크플로를 강제하지 않는다**  
   → QA 경로는 여전히 빠르게 유지

4. **프롬프트로만 계획을 관리하지 않는다**  
   → outline, evidence, draft는 반드시 파일이어야 한다

5. **서브에이전트에게 최종 산문을 생성하게 하지 않는다**  
   → 서브에이전트는 수집만, 합성은 메인 에이전트에서

6. **Gemini 자기 검증을 법률 논거 지원에 신뢰하지 않는다**  
   → `verify_claim_support`는 별도 증거 매칭 패스 필요

7. **제너릭 자율 에이전트 스웜을 만들지 않는다**  
   → 명확한 아티팩트를 가진 단순한 타입 워크플로

---

## 구현 단계

### 1단계: 분석 기반 (고임팩트, 낮은 복잡도)
- `map_document` 구현
- `bulk_read` 구현
- 시스템 프롬프트에 분석 모드 추가

### 2단계: 증거 구조화
- `extract_to_evidence` 구현
- 서브에이전트: JSON 블롭 반환 → `evidence.jsonl` 누적으로 변경

### 3단계: 서면 작성
- `create_outline` 구현
- `write_section` 구현
- `verify_claim_support` 구현

### 4단계: 루프 강화
- 분석 모드 턴 예산 확대 (25 → 50)
- 페이즈 간 체크포인트 추가

---

## 영향받는 파일

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `case_agent/tools/document_tools.py` | **신규** | map_document, bulk_read, extract_to_evidence |
| `case_agent/tools/writing_tools.py` | **신규** | create_outline, write_section |
| `case_agent/tools/agent_tools.py` | 수정 | verify_claim_support 추가 |
| `case_agent/tools/search.py` | 수정 | bulk_read 위한 배치 지원 |
| `case_agent/prompts/main_system.md` | 수정 | 분석 모드 / 서면 작성 모드 추가 |
| `case_agent/loop/query.py` | 수정 | 모드별 턴 예산, 체크포인트 |
| `case_agent/subagents/explore.py` | 수정 | JSON 블롭 → 파일 누적 |

---

## 검증 방법

1. **분석 모드**: 50페이지 공소장 전체 분석 → `evidence.jsonl` 생성 → 사용 턴 수 측정
2. **서면 작성**: `create_outline` → `write_section` × N → `verify_claim_support` 통과율
3. **QA 회귀**: 기존 `benchmark_indictment.json` 점수 유지 확인
4. **논거 검증**: 인용이 주장을 실제로 지원하지 않는 케이스 감지율
