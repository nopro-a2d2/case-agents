---
name: brief_civil
description: 민사 준비서면 작성 룰 — REFUTED/ENFORCED/REASON 3축 논증, narrative-and-rebuttal, evidence-citation, tone-and-style 통합 가이드.
when_to_use: 민사 준비서면(civil_brief) 본문을 직접 작성하거나 brief_civil 서브에이전트에 위임할 때 본 SKILL 의 룰을 함께 전달.
allowed-tools: smart_search, read_evidence, list_evidence, write_file, verify_citations, check_completeness
argument-hint: <focus>
---

# 민사 준비서면 작성 룰

`brief_civil` 서브에이전트의 동작을 보강하는 도메인 룰. 본 스킬을 직접 호출하면 메인
에이전트가 룰을 읽고 직접 작성하거나 위임 prompt 에 룰 핵심을 포함시킬 수 있다.

## 1. 3축 논증 프레임워크 — Plan 단계에서 사용

| 축 | 정의 | 작성 시 요구 |
|----|------|--------------|
| **REFUTED** | 상대방의 주장 중 반박해야 할 핵심 사실 | 상대방 인용 1개 + 반박 근거 인용 1개 이상 |
| **ENFORCED** | 우리 측이 입증해야 할 핵심 사실 | 입증 자료 인용 1개 이상 |
| **REASON** | 위 두 축을 결론으로 연결하는 법리 | 적용 법령·판례·요건사실 분석 |

Plan 파일에 각 축별로 항목을 표 형태로 정리한 뒤 본문을 작성한다.

## 2. Narrative-and-Rebuttal 패턴

### Option A: General Defense (시간순 사건 경위)
- 첫 서면(Brief 1) 또는 "사건 개요" 섹션에서만 사용.
- 시간 순으로 사실관계를 전개. 각 사실 문장에 인용 1개 이상.

### Option B: Targeted Rebuttal (쟁점 중심 즉각 반박) — 후속 서면 기본값
- 일반적 배경 설명을 생략하고 다음 패턴 사용:

```
가. [증거명](@@[id]) 에 관하여
   상대방은 [증거명](@@[id]) 을 근거로 [주장] 을 주장합니다.
   그러나 이는 사실과 다릅니다. [반박 논리](@@[id]).
   따라서 [결론].
```

상대방 주장이 명확히 식별되는 경우 Option B 가 항상 우선이다.

### 당사자 발화 인용
- "원고는 …라고 주장합니다", "피고는 …라고 진술하였습니다" 패턴.
- 발화 인용 직후 인용 anchor 부착.

## 3. Evidence-Citation 형식

- 인용은 `@@[id]` 한 형식만. minsa-written-ai 의 `@@[id]` 는 사용하지 않는다.
- 문장 끝 괄호로 표기: `… 입니다 (@@[3]).`
- 인용 문구는 **반드시 read_evidence(id, start_page=…) 로 verbatim 확보 후 paste**. paraphrase 금지.
- 한 사실에 여러 자료가 필요하면 인용을 연속 부착: `(@@[1]; @@[계약서])`.
- 갑/을 호증 번호가 사건에 도입되어 있으면 본문에 "갑 제5호증(@@[5])" 형태로 함께 표기. 페이지 정보가 필요하면 산문에 "갑 제5호증 제2쪽" 처럼 자연어로 적는다.

## 4. Tone-and-Style

- 법조 문체: "~인바", "~는바", "~하였는바", "그러므로", "따라서".
- 당사자 표기: 사건의 합의된 표현 우선 (원고 / 피고 / 원고대리인 / 피고대리인). 
  소장·기존 서면을 read_file 로 확인해 표기 통일.
- 소제목: `### 가. ...`, `### 나. ...` 한글 자모 번호 우선. 아라비아 숫자도 허용
  (`### 1. ...`).
- 영어 섹션 헤더 금지. 모든 헤딩 한국어.
- 최상위 헤딩 `##`. `#` 금지.

## 5. 법리 (REASON) 작성 가이드

- 적용 법령·판례 인용은 wiki-output 또는 인용 가능한 출처가 있는 경우에만 (모델
  일반지식 기반 인용 금지).
- 요건사실 분석: 요건별로 구분해 (1) 요건 (2) 우리 사실의 충족/미충족 (3) 인용 의
  3단 구조.
- 판례 인용 시 사건 번호와 wiki-output 의 해당 섹션을 anchor 로 부착.

## 6. Self-review (작성 후, verify 호출 전)

- [ ] 모든 ENFORCED 사실에 입증 자료 인용 부착
- [ ] 모든 REFUTED 항목에 상대방 인용 + 반박 근거 인용 모두 부착
- [ ] 결론이 청구취지와 일치
- [ ] 인용 ≥ 5개 (check_completeness civil_brief 규칙)
- [ ] 헤딩 키워드 "청구", "주장", "결론" 등장
- [ ] verify_citations 실패 0, check_completeness("civil_brief", ...) issues 빈 리스트
