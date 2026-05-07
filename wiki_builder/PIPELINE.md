# LLM Wiki Builder — 전체 빌드 파이프라인 상세

**진입점:** `python -m wiki_builder --case <사건폴더> [--phase N]`
**위치:** `/data/nopro/case-agents/wiki_builder/`
**모델:** `gemini-3.1-flash-lite-preview` (Vertex AI ADC)
**입출력 규칙:** `<case>/json/` (입력) → `<case>/wiki-output/` (위키) + `<case>/cache/` (재실행용 캐시)

## 0. 부트스트랩 (`__main__.py`)

1. `dotenv.load_dotenv()` — Vertex 인증·Langfuse 키를 `os.environ` 으로 주입 (다른 import 보다 **먼저**).
2. `apply_case_path(args.case)` — `wiki_settings` 에 `JSON_DIR / WIKI_OUTPUT_DIR / CACHE_DIR` 파생 경로 주입.
3. `setup_logging()` — `logs/pipeline_YYYYMMDD_HHMMSS.log` + 콘솔 동시 출력.
4. `ensure_dirs()` — `wiki-output/{sources,entities,concepts}` 생성.
5. **문서 로드** (`loader.load_all_documents`)
   - 모든 `*.json` 을 비동기 병렬로 `Document` 로 파싱.
   - `sort_by_category` 로 **공소장 → 수사보고서 → 진술 → 참조법문서 → 기타** 순서 고정.
   - 이 순서가 이후 모든 phase 의 `doc_order` 가 되어, **공소장이 가장 먼저 entity/concept 정체성을 형성** 한다.
6. 입력 문서 카테고리 카운트 + 총 토큰 로그 → Langfuse 트레이스 시작.

## Phase 1 — 소스 페이지 컴파일 (실시간 LLM, 동시성 15)

`realtime_compiler.run_phase1_realtime` + `compiler.py` 보조.

각 `Document` 1건당 LLM 1회 호출:

- **프롬프트:** `SOURCE_COMPILE_PROMPT` (system: `SOURCE_COMPILE_SYSTEM`)
  - 인풋: `doc_id`, `name`, `category`, `person`, `total_page`, `token_count`, `full_text` (페이지 마커 `[페이지 N]` 포함).
- **structured output:** `response_schema = CompileResultLLM` (Gemini JSON mode, `temperature=0.1`).
  - `summary` (문서 요약)
  - `key_facts`: `dates / amounts / persons / organizations / legal_provisions` — 각 fact 에 출처 페이지 번호 배열.
  - `detailed_content`: 사실 단위 문장 리스트 (`text`, `pages`).
  - `entities`: `{name_ko, type∈person|org|place|other}`.
  - `concepts`: `{name_ko, description}`.
- **캐시:** `cache/phase1_results/{doc_id}.json` 에 raw JSON 저장.
  - 캐시 hit 시 LLM 호출 skip, 단 파싱 실패한 파일은 즉시 삭제 후 재호출.
- **Phase 1.5 검증** (`verifier.verify_compile_result`): citation back-check — `key_facts.*.pages` 가 실제 문서 페이지 텍스트에 등장하는지 검증, 실패 fact 는 `result.verification_failures` 로 분리 (페이지에는 남지만 환각 표시).
- **출력:** `write_source_page` 가 `wiki-output/sources/source-{doc_id}.md` 생성. frontmatter 에 `id, title, category, person, pages, tokens, schema_version` 등 + 본문에 요약/사실/상세 사실 단위 누적.
- 동시성 `Semaphore(15)`. 50건마다 진행률 로그.

## Phase 2 — 엔티티 점진적 성장 (LLM 호출 0회)

`entity_extractor.run_phase2`.

핵심 아이디어: **LLM 은 Phase 1 에서 이미 entity 를 추출했으므로, 여기는 이름 매칭으로 누적만 한다.**

문서 순서대로(공소장 우선) 처리:

1. `load_registry("entity")` — 기존 `wiki-output/entity_registry.json` 로드 (없으면 빈 레지스트리).
2. 각 문서의 `result.entities` 순회:
   - `registry.find_by_name(name_ko)` 로 `name_index` 조회.
   - 있으면 `add_source(doc_id, pages)` 로 출처 누적.
   - 없으면 `register(...)` — `entity-{NNN:03d}` 신규 ID 부여, `wiki-output/entities/entity-NNN.md` 경로 등록.
3. 각 entity 별 `_extract_entity_info(result, entity)` 가 fact 들을 grep 매칭으로 모아 RAW 라인 생성:
   - `key_facts.persons / organizations / dates / amounts / detailed_content` 중 `entity.name_ko` 가 포함된 것들 + 출처 페이지.
4. `append_managed_raw_subsection(entry, doc_id, info, is_concept=False)` — 페이지의 `## RAW` 섹션 안에 `### source-{doc_id}` 서브섹션을 **append-only** 로 추가.
   - 동시 쓰기 방지: 문서 단위는 `Semaphore(10)` 병렬, registry 변경은 `registry_lock`, 같은 entity 페이지 동시 쓰기는 `entity_locks[target_id]` 로 직렬화.
5. 50건마다 registry 저장. 끝에 한 번 더 저장.

**resumability:** registry 의 `entry.source_ids` 에 이미 처리한 `doc_id` 가 들어있으면 그 문서는 skip.

## Phase 2.5 — Entity Alias Canonicalization (LLM)

`alias_resolver.run_phase2_5` → `canonicalize("entity")`.

목적: "윤 사장" / "윤경림" / "윤 대표" 같은 **표기 분기를 하나로 병합**.

1. type 별로 (person / org / place / other) bucket 분리.
2. 각 bucket 안에서 이름 알파벳순 정렬 후 60개 단위 batch.
3. 각 batch → LLM 1회 호출 (`ALIAS_GROUP_PROMPT`, JSON 응답, `temperature=0`):
   - 출력: `[["entity-001","entity-007"], ["entity-002"], ...]`.
4. `_normalize_groups` 로 응답 무결성 보정 (알 수 없는 ID 제거, 누락은 1-element 그룹).
5. `absorb_group(registry, group, write_entity_page)`:
   - `source_ids` 가 가장 많은 entry 를 **canonical** 선택.
   - 흡수 entry 페이지의 `## RAW` 서브섹션을 canonical 페이지에 `merge_raw_subsections_from_body` 로 idempotent merge.
   - `aliases` / `source_ids` / `source_page_map` 을 union.
   - 흡수 페이지 파일 삭제, `registry.entries.pop`.
   - canonical 페이지의 frontmatter (aliases, source_count, sources block) 재기록.
6. 흡수 결정은 `wiki-output/alias_decisions_entity.md` 로 기록 → **동명이인 오병합 수동 검토용**.

## Phase 3 — 개념 점진적 성장

`concept_extractor.run_phase3`. Phase 2 와 완전히 동일한 패턴이지만 대상이 `result.concepts` (type=`topic`).

매칭 grep 풀: `detailed_content`, `key_facts.dates/amounts/legal_provisions`. 페이지는 `wiki-output/concepts/concept-NNN.md`.

## Phase 3.5 — Concept Alias Canonicalization

`alias_resolver.run_phase3_5` → `canonicalize("concept")`. Phase 2.5 와 동일 로직, prefix 만 `concept`.

## Phase synth — Entity / Concept 합성 (LLM 1회/페이지)

`synthesizer.run_synthesis`.

지금까지 entity/concept 페이지에는 raw fact append 만 되어 있었고, 사람이 읽을 수 있는 prose 가 없다. 이 phase 가 그것을 만든다.

각 entry 별:

1. `read_page` → frontmatter `meta` + 본문 분리.
2. `_needs_synthesis(meta)`: `synth_source_count != source_count` 면 dirty (새 출처 추가 후 재합성 필요). `--force-synth` 면 무조건.
3. `_extract_raw(body)` 로 `## RAW` 섹션 텍스트만 추출 (8000자 cap).
4. LLM 호출:
   - entity → `ENTITY_SYNTHESIS_PROMPT`, concept → `CONCEPT_SYNTHESIS_PROMPT`, system: `ENTITY_SYNTHESIS_SYSTEM`, `temperature=0.2`.
5. `set_managed_synthesis(entry, body, is_concept)` — 페이지의 `## SYNTHESIS` 섹션을 새 본문으로 교체. RAW 섹션은 불변.
6. `_stamp_synth_count(path, len(entry.source_ids))` → 다음 빌드의 dirty 비교 기준.

동시성 `Semaphore(8)`.

## Phase 4 — 교차 참조 [[wikilink]] 자동 삽입

`cross_ref.run_phase4` 가 멱등성을 보장하기 위해 4단계 실행:

- **4a `sanitize_wiki_pages`** — LLM 산출물의 `[[[...]]]` 삼중 괄호를 `[[...]]` 로 정규화.
- **4b `strip_all_wikilinks`** — 기존 `[[path|label]]` → `label`, `[[path]]` → `path` 로 plain text 복원. 단 sentinel `## 출처` 블록(`SOURCES_BLOCK_START/END` 사이)은 마스킹해 보존.
- **4c `run_phase4`**:
  1. `_build_name_to_link` — entity + concept registry 의 `name_ko` 와 모든 `aliases` 를 `[[file|name]]` 으로 매핑.
  2. 모든 `sources / entities / concepts` 페이지에 대해, sentinel 블록 마스킹 → 줄 단위 처리:
     - `#` 시작 줄(헤딩)은 스킵.
     - 이미 존재하는 `[[...]]` span 은 placeholder 로 마스킹해서 중첩 링크 방지.
     - **이름 길이 내림차순** 으로 치환 — 부분 매칭 문제 방지 ("윤경림" 이 "윤" 보다 먼저 매칭).
     - 줄당 한 이름은 첫 발생만 치환 (`replace(..., 1)`).
- **4d post-sanitize** — 혹시 link 삽입 결과가 다시 malformed 가 됐는지 한 번 더 검증.

이 phase 는 LLM 호출 없음, 순수 텍스트 변환.

## Phase 5 — index.md / overview.md 생성

`index_generator.run_phase5`.

- **`index.md`** (LLM 호출 없음):
  - 인물 / 조직 / 기타 / 개념을 `len(source_ids)` 내림차순으로 나열, 각 항목에 클릭 가능한 상대 경로 링크.
  - 카테고리별 소스 문서 (카테고리당 50개 cap, 초과는 "... 외 N개").
  - 상위 30개 키워드 인덱스 표.
- **`overview.md`** (LLM 호출 1회):
  - 각 source 페이지 frontmatter 에서 추출한 summary 를 카테고리별로 묶어 `OVERVIEW_PROMPT` 에 주입 (`temperature=0.3`).
  - 사건 전체에 대한 계층적 prose 개요 생성.

`source_pages` 는 `__main__` 이 미리 `frontmatter.load` + `## 요약` 섹션 추출로 준비해서 넘김.

## Phase 6 — 린트 (LLM 호출 없음)

`linter.run_phase6`.

1. `_collect_all_pages` — sources / entities / concepts 페이지 전체 수집.
2. `find_orphan_pages` — `[[wikilink]]` 정규식으로 모든 참조 대상 수집 → entity/concept 페이지 중 한 번도 참조되지 않는 것 (sources 는 제외 — 참조 안 돼도 OK).
3. `find_broken_links` — 존재하지 않는 페이지를 가리키는 wikilink.
4. `count_stats` — 페이지 수, wikilink 총 개수, 총 문자 수.
5. `wiki-output/lint_report.md` 로 출력.

## Phase 7 — 임베딩 인덱스 (Hybrid 검색 Tier 2)

`embedder.run_phase7`. **Phase 4 이후** 에 실행해야 함 (cross_ref 가 본문 변경하므로).

대상: `entities/`, `concepts/`, `sources/` 모든 `.md`.

1. **`_scan_pages`** — 각 페이지에서 `name_ko + aliases + 본문` 을 `build_doc_text` 로 합성. source 는 6000자, 그 외는 2000자 cap. `compute_content_hash(text, model, dim)` 로 SHA1 해시 계산.
2. **`_load_existing`** — 이전 빌드의 `vectors.npy / index.json / manifest.json` 로드.
   - `manifest.model` 또는 `dim` 변경 → 전체 재빌드.
   - 정합성 깨지면 (`vectors.shape[0] != len(index)`) 전체 재빌드.
   - 정합성 OK 면 `file → row_index` 매핑 보관 (재사용용).
3. **변경분 식별** — `old_files[file] == p["hash"]` 인 페이지는 `reuse`, 나머지는 `to_embed`.
4. **`_embed_batches`** — `to_embed` 의 `doc_text` 만 100개 배치 × 동시성 10 으로 임베딩 (`embed_texts` → `gemini-embedding-2`, 768 dim, L2 정규화).
5. **합성** — `pages` 원순서 보존하며, 신규는 새 벡터, 재사용은 `old_vectors[old_file_to_row[file]]` 에서 그대로 복사.
6. **저장:**
   - `cache/embeddings/vectors.npy` — `(N, 768) float32`.
   - `cache/embeddings/index.json` — 행 순서대로 `{file, id, name_ko, type}`.
   - `cache/embeddings/manifest.json` — `{model, dim, files: {file: sha1}}` (다음 빌드 idempotency 키).

검색 시 `wiki_settings.SEMANTIC_TOP_K=8`, `SEMANTIC_MIN_SIM=0.70` 으로 사용.

## 핵심 설계 패턴 요약

| 패턴 | 적용 |
|---|---|
| **Append-only RAW + 별도 SYNTHESIS** | Phase 2/3 에서 LLM 호출 0회로 누적, Phase synth 에서 1페이지 1호출로 합성. 새 문서 추가 시 RAW append → synth_source_count dirty → 자동 재합성. |
| **카테고리 정렬 (공소장 우선)** | entity/concept 의 canonical 이름을 가장 권위있는 문서에서 먼저 결정. |
| **캐시 기반 재실행** | `cache/phase1_results/` (Phase 1), registry JSON (Phase 2/3), `cache/embeddings/manifest.json` (Phase 7) 으로 phase 별 재실행 가능. |
| **멱등성** | Phase 4 의 sanitize → strip → insert 3단계, Phase 7 의 hash 기반 변경분 임베딩. |
| **무결성 검증** | Phase 1.5 citation back-check, Phase 2.5/3.5 alias 그룹 정규화 + 결정 로그, Phase 6 린트 (orphan/broken). |
| **동시성 제어** | Phase 1 `Semaphore(15)`, Phase 2/3 `Semaphore(10)` + `registry_lock` + per-entry lock, Phase synth `Semaphore(8)`, Phase 7 `Semaphore(10)` × 100 batch. |
| **관측성** | 모든 LLM 호출 `log_generation` 으로 Langfuse 전송 + `get_token_stats` 로 누적 토큰 집계. |

## 산출물 디렉터리

```
<case>/
├── json/                           # 입력
├── cache/
│   ├── phase1_results/{doc_id}.json
│   └── embeddings/{vectors.npy, index.json, manifest.json}
└── wiki-output/
    ├── sources/source-{doc_id}.md
    ├── entities/entity-{NNN}.md
    ├── concepts/concept-{NNN}.md
    ├── entity_registry.json
    ├── concept_registry.json
    ├── alias_decisions_entity.md
    ├── alias_decisions_concept.md
    ├── index.md
    ├── overview.md
    └── lint_report.md
```
