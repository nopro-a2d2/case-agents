"""위키 빌더 프롬프트 (소스 컴파일 / 엔티티·개념 추출 / 개요)"""

SOURCE_COMPILE_SYSTEM = """\
당신은 한국어 법률 문서 전문 위키 편집자입니다.
법률 문서를 읽고 구조화된 위키 소스 페이지로 컴파일하는 것이 임무입니다.
모든 출력은 한국어로 작성하세요."""

SOURCE_COMPILE_PROMPT = """\
다음 법률 문서를 위키 소스 페이지로 컴파일하세요.

## 문서 정보
- 증거번호(ID): {doc_id}
- 문서명: {name}
- 카테고리: {category}
- 관련 인물: {person}
- 총 페이지: {total_page}
- 토큰 수: {token_count}

## 문서 전문
{full_text}

## 출력 규칙
1. **요약** (3-5문장): 문서의 핵심 내용과 의의
2. **핵심 사실** (구조화된 목록):
   - dates: 모든 날짜를 YYYY.MM.DD 형식으로 (날짜, 이벤트, 페이지)
   - amounts: 모든 금액 (금액, 맥락, 페이지)
   - persons: 모든 인물 실명과 직책 (이름, 역할, 페이지)
   - organizations: 모든 조직/회사 (이름, 역할, 페이지)
   - legal_provisions: 모든 법적 조항/죄명
3. **상세 내용** (`detailed_content`): 원문의 핵심 정보를 한 사실 단위(보통 1문장)씩
   `{{"text": "...", "pages": [N, M]}}` 객체 배열로 출력하세요.
4. **관련 엔티티**: 문서에 등장하는 주요 인물/조직/장소 목록
5. **관련 개념**: 문서의 주요 법률 개념/사건 유형 목록

## 출처 페이지 규칙 (중요)
문서 본문은 `[페이지 N]` 마커로 페이지가 구분되어 있습니다.
- 모든 dates/amounts/persons/organizations 항목, 그리고 detailed_content의 모든 객체에
  해당 사실이 등장한 페이지 번호 배열 `pages`를 반드시 채워주세요 (정수만).
- 한 사실이 여러 페이지에 걸쳐 나오면 모든 페이지 번호를 나열 (예: [3, 4]).
- 페이지 마커가 분명하지 않은 경우에만 빈 배열 []을 허용합니다.
- detailed_content의 `text` 필드에는 `(p.N)`, `(source-...)` 같은 출처 표기를
  **절대 포함하지 마세요**. 페이지는 `pages` 필드로만 표현합니다.

## 중요
- 원문에 없는 정보를 추가하지 마세요 (환각 금지)
- 날짜, 금액, 인명, 법조항은 절대 생략하지 마세요
- 익명 인물은 익명으로 유지하세요

반드시 아래 JSON 형식으로만 출력하세요:
{{
  "summary": "요약 텍스트",
  "key_facts": {{
    "dates": [{{"date": "YYYY.MM.DD", "event": "설명", "pages": [3]}}],
    "amounts": [{{"amount": "금액", "context": "맥락", "pages": [5]}}],
    "persons": [{{"name": "이름", "role": "직책/역할", "pages": [1, 2]}}],
    "organizations": [{{"name": "조직명", "role": "역할", "pages": [1]}}],
    "legal_provisions": ["법조항"]
  }},
  "detailed_content": [
    {{"text": "사실1 본문", "pages": [1]}},
    {{"text": "사실2 본문", "pages": [3, 4]}}
  ],
  "entities": [{{"name_ko": "이름", "type": "person|org|place|other"}}],
  "concepts": [{{"name_ko": "개념명", "description": "설명"}}]
}}"""

ENTITY_SYNTHESIS_SYSTEM = """\
당신은 한국어 법률 사건 위키 편집자입니다.
원시 사실 섹션(RAW)을 읽고 자연스러운 prose 로 합성합니다.
새 사실 추가나 추측은 절대 금지 — RAW 안의 정보만 사용."""

ENTITY_SYNTHESIS_PROMPT = """\
다음은 위키 entity "{name_ko}" 페이지의 RAW 사실 섹션입니다.
출처별로 누적된 fact 들을 자연스러운 prose 로 합성하세요.

## RAW 섹션
{raw}

## 출력 규칙
- 모든 사실은 RAW 안에서만 발췌 (외부 지식 금지, 추측 금지)
- 각 사실 끝의 `(source-X:p1,p2)` citation 토큰을 보존
- 시간순 또는 주제별로 자유롭게 정리
- 마크다운 형식, 짧고 밀도 높게 (3~10문장)
- 새 wikilink `[[...]]` 는 추가하지 마세요 (Phase 4 가 처리)
- frontmatter / 제목 (#) / sentinel 주석은 출력하지 마세요 — 본문만"""

CONCEPT_SYNTHESIS_PROMPT = """\
다음은 위키 concept "{name_ko}" 페이지의 RAW 사실 섹션입니다.
출처별로 누적된 fact 들을 prose 로 합성하세요.

## RAW 섹션
{raw}

## 출력 규칙
- 모든 사실은 RAW 안에서만 발췌
- 각 사실 끝의 `(source-X:p1,p2)` citation 토큰을 보존
- 정의 → 사실관계 → 법적 쟁점 순서가 자연스러우면 그렇게 정리
- 마크다운, 짧고 밀도 높게 (3~10문장)
- 새 wikilink 추가 금지, 제목·sentinel 출력 금지"""

OVERVIEW_PROMPT = """\
다음은 한국 법률 사건의 카테고리별 요약입니다.
이 요약들을 종합하여 사건 전체 개요를 작성하세요.

{category_summaries}

## 규칙
- 사건의 전체적인 맥락과 흐름을 서술
- 핵심 인물, 조직, 쟁점을 포함
- 시간순으로 정리
- 한국어로 작성
- 마크다운 형식"""
