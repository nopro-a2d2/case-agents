"""Phase 2.5 / 3.5 — alias canonicalization.

LLM 호출 1~N 회로 entity/concept registry 의 동의어 항목을 그룹화하고,
각 그룹에서 가장 source 수가 많은 entry 를 canonical 로 선택해 나머지를 흡수한다.

흡수 정책:
- canonical.aliases 에 흡수 entry 의 name_ko 와 기존 alias 추가
- canonical.source_ids/source_page_map 에 흡수 entry 정보 union
- name_index 에서 흡수 entry name → canonical id 로 자동 갱신 (add_alias)
- 흡수 entry 페이지 파일 삭제, 본문은 canonical 본문 끝에 raw concat 으로 append
- 결정 로그를 ``wiki-output/alias_decisions_{entity|concept}.md`` 에 기록 (수동 검토)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable

from google import genai

from wiki_builder.config import wiki_settings
from wiki_builder.llm import get_genai_client
from wiki_builder.models import Registry, RegistryEntry
from wiki_builder.observability import log_generation
from wiki_builder.wiki_store import (
    _extract_synth,
    load_registry,
    merge_raw_subsections_from_body,
    read_page,
    save_registry,
    wiki_dir,
    write_concept_page,
    write_entity_page,
)

logger = logging.getLogger(__name__)

ALIAS_GROUP_SYSTEM = """\
당신은 한국어 법률 사건 위키의 엔티티 정규화 전문가입니다.
같은 인물·조직·개념을 가리키는 다른 표기를 찾아 그룹화합니다."""

ALIAS_GROUP_PROMPT = """\
다음 {kind} 목록에서 **같은 대상** 을 가리키는 항목들을 그룹화하세요.

## 그룹화 규칙
- 직책+이름 같은 자연스러운 변형 ("윤 사장" + "윤경림") 은 같은 그룹.
- 약칭/풀네임 ("KT" + "주식회사 KT") 은 같은 그룹.
- **동명이인 가능성이 있으면 분리** (확신할 때만 묶기).
- **인수/합병/지분관계라도 별도 법인이면 분리** ("KT" 와 "KT 가 인수한 하나로통신",
  "현대자동차" 와 "현대모비스" 는 서로 다른 entity — 같은 그룹 금지).
- 표기 유사도가 0 에 가까운 쌍 (이름이 거의 겹치지 않음) 은 사전지식이 아닌
  본문 설명으로만 판단하고, 확신이 없으면 분리하세요.
- 모든 입력 ID 가 정확히 한 그룹에 속해야 함 (1-element 그룹 포함).

## 입력 형식
각 항목은 `- {{id}}: {{이름}} ({{N}}개 문서)` 한 줄로 표기되며, 가능한 경우
바로 다음 줄에 `    설명: ...` 형태로 요약 1~2문장이 붙습니다.
설명이 있으면 같은 대상 판단의 **1순위 근거** 로 활용하세요.

## 입력
{items}

## 출력
JSON 배열, 각 그룹은 ID 문자열 배열.
예: [["entity-001", "entity-007"], ["entity-002"]]"""


_BATCH_SIZE = 60
_DESC_MAX_CHARS = 160

_WIKILINK_RE = re.compile(r"\[\[[^\]|]*\|([^\]]+)\]\]|\[\[([^\]]+)\]\]")
_CITATION_RE = re.compile(r"\(\s*source-[^)]*\)")
_HEADING_RE = re.compile(r"^#+\s.*$", re.MULTILINE)


def _clean_synth_prose(text: str) -> str:
    """SYNTHESIS prose 에서 wikilink 표시텍스트만 남기고 citation·헤더·여분 공백 제거."""
    text = _HEADING_RE.sub("", text)
    text = _WIKILINK_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _CITATION_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_description(entry: RegistryEntry) -> str:
    """entry 의 wiki 페이지 SYNTHESIS 첫 문장 1~2개 (~160자) 를 평문으로 반환.

    페이지가 없거나 합성이 비어 있으면 빈 문자열. LLM 입력 보강 전용이므로
    실패 시 silent fallback (정규화 자체를 막지 않음)."""
    path = wiki_dir() / entry.file
    if not path.exists():
        return ""
    try:
        _, body = read_page(path)
    except Exception:
        return ""
    synth = _extract_synth(body)
    if not synth:
        return ""
    cleaned = _clean_synth_prose(synth)
    if not cleaned:
        return ""
    if len(cleaned) <= _DESC_MAX_CHARS:
        return cleaned
    cut = cleaned[:_DESC_MAX_CHARS]
    last_period = max(cut.rfind("."), cut.rfind("。"), cut.rfind("다 "))
    if last_period >= 40:
        return cut[: last_period + 1].strip()
    return cut.rstrip() + "…"


def _format_items(
    entries: list[RegistryEntry],
    descriptions: dict[str, str] | None = None,
) -> str:
    descriptions = descriptions or {}
    lines: list[str] = []
    for e in entries:
        lines.append(f"- {e.id}: {e.name_ko} ({len(e.source_ids)}개 문서)")
        desc = (descriptions.get(e.id) or "").strip()
        if desc:
            lines.append(f"    설명: {desc}")
    return "\n".join(lines)


async def _group_batch(
    client: genai.Client,
    model: str,
    kind: str,
    batch: list[RegistryEntry],
    descriptions: dict[str, str] | None = None,
) -> list[list[str]]:
    """LLM 호출 1회로 batch 안의 entry 들을 그룹화."""
    if len(batch) <= 1:
        return [[e.id] for e in batch]

    prompt = ALIAS_GROUP_PROMPT.format(
        kind=kind, items=_format_items(batch, descriptions)
    )
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config={
            "system_instruction": ALIAS_GROUP_SYSTEM,
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    )
    text = response.text or "[]"
    in_tok = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
    out_tok = (
        response.usage_metadata.candidates_token_count if response.usage_metadata else 0
    )
    log_generation(
        "alias-group",
        model,
        f"{kind}/{len(batch)}",
        text[:200],
        input_tokens=in_tok or 0,
        output_tokens=out_tok or 0,
    )

    try:
        groups = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("alias group JSON 파싱 실패 (kind=%s) — 1-element 로 fallback", kind)
        return [[e.id] for e in batch]

    return _normalize_groups(groups, {e.id for e in batch})


def _normalize_groups(raw: Any, valid_ids: set[str]) -> list[list[str]]:
    """LLM 출력의 무결성 검증: 알 수 없는 ID 제거, 누락된 입력은 1-element 그룹으로 보충."""
    if not isinstance(raw, list):
        return [[i] for i in valid_ids]
    seen: set[str] = set()
    out: list[list[str]] = []
    for g in raw:
        if not isinstance(g, list):
            continue
        cleaned: list[str] = []
        for eid in g:
            if isinstance(eid, str) and eid in valid_ids and eid not in seen:
                cleaned.append(eid)
                seen.add(eid)
        if cleaned:
            out.append(cleaned)
    for missing in valid_ids - seen:
        out.append([missing])
    return out


async def _group_all(
    client: genai.Client,
    model: str,
    kind: str,
    entries: list[RegistryEntry],
    descriptions: dict[str, str] | None = None,
) -> list[list[str]]:
    """이름순 정렬 후 batch 단위로 LLM 그룹화 — 유사 이름이 같은 batch 에 모이도록."""
    sorted_entries = sorted(entries, key=lambda e: e.name_ko)
    batches = [
        sorted_entries[i : i + _BATCH_SIZE]
        for i in range(0, len(sorted_entries), _BATCH_SIZE)
    ]
    results = await asyncio.gather(
        *[_group_batch(client, model, kind, b, descriptions) for b in batches]
    )
    flat: list[list[str]] = []
    for r in results:
        flat.extend(r)
    return flat


def absorb_group(
    registry: Registry,
    group: list[str],
    page_writer: Callable[[RegistryEntry, str | None], Any],
) -> tuple[str, list[str]]:
    """그룹에서 source 수 max 인 entry 를 canonical 로 선택, 나머지를 흡수.

    절차:
      1. 흡수 entry 의 RAW source 서브섹션을 canonical 의 RAW 로 merge (idempotent)
      2. alias / source_ids / source_page_map 을 canonical 로 union
      3. 흡수 페이지 파일 삭제, registry.entries 에서 제거
      4. canonical 페이지를 page_writer 로 한 번 더 호출해 frontmatter (sources/aliases) 갱신

    Returns: (canonical_id, absorbed_ids)
    """
    if len(group) < 2:
        return (group[0] if group else "", [])

    canonical_id = max(group, key=lambda i: len(registry.entries[i].source_ids))
    absorbed_ids = [i for i in group if i != canonical_id]
    canonical = registry.entries[canonical_id]
    is_concept = page_writer is write_concept_page

    wdir = wiki_dir()
    for aid in absorbed_ids:
        ab = registry.entries.get(aid)
        if ab is None:
            continue

        ab_path = wdir / ab.file
        if ab_path.exists():
            _, ab_body = read_page(ab_path)
            merge_raw_subsections_from_body(canonical, ab_body, is_concept=is_concept)
            ab_path.unlink()

        registry.add_alias(canonical.id, ab.name_ko)
        for alias in ab.aliases:
            registry.add_alias(canonical.id, alias)
        for sid in ab.source_ids:
            registry.add_source(
                canonical.id, sid, pages=ab.source_page_map.get(sid, [])
            )

        registry.entries.pop(aid, None)

    # frontmatter (aliases, source_count, sources block) 최신화
    page_writer(canonical, None)
    return (canonical_id, absorbed_ids)


def _write_decisions(name: str, decisions: list[dict]) -> None:
    if not decisions:
        return
    path = wiki_dir() / f"alias_decisions_{name}.md"
    lines = [
        f"# {name} alias 정규화 결정 로그",
        "",
        "_LLM 이 같은 대상으로 판단해 흡수한 그룹 목록. 동명이인 오병합 여부를 수동 검토하세요._",
        "",
    ]
    for d in decisions:
        lines.append(
            f"## {d['canonical_name']} (`{d['canonical']}`) — type=`{d['type']}`"
        )
        for ab in d["absorbed"]:
            lines.append(f"- `{ab['id']}` {ab['name']} → 흡수")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


async def canonicalize(registry_name: str, prefix: str) -> dict:
    """entity/concept registry 정규화 1회 패스. 통계 dict 반환."""
    registry = load_registry(registry_name, prefix=prefix)
    if not registry.entries:
        logger.info("정규화 skip: %s registry 비어있음", registry_name)
        return {"groups": 0, "absorbed": 0, "registry": 0}

    client = get_genai_client()
    model = wiki_settings.REALTIME_MODEL
    page_writer = (
        write_entity_page if registry_name == "entity" else write_concept_page
    )

    type_buckets = sorted({e.type for e in registry.entries.values()})
    decisions: list[dict] = []
    absorbed_total = 0
    group_total = 0

    for tname in type_buckets:
        entries = [e for e in registry.entries.values() if e.type == tname]
        if len(entries) < 2:
            continue
        logger.info(
            "정규화: %s type=%s 항목 %d개", registry_name, tname, len(entries)
        )
        descs = {e.id: _extract_description(e) for e in entries}
        groups = await _group_all(client, model, tname, entries, descs)
        for g in groups:
            if len(g) < 2:
                continue
            name_snapshot = {
                i: registry.entries[i].name_ko
                for i in g
                if i in registry.entries
            }
            canonical_id, absorbed_ids = absorb_group(registry, g, page_writer)
            if not absorbed_ids:
                continue
            absorbed_total += len(absorbed_ids)
            group_total += 1
            decisions.append(
                {
                    "type": tname,
                    "canonical": canonical_id,
                    "canonical_name": registry.entries[canonical_id].name_ko,
                    "absorbed": [
                        {"id": i, "name": name_snapshot.get(i, "?")}
                        for i in absorbed_ids
                    ],
                }
            )

    save_registry(registry, registry_name)
    _write_decisions(registry_name, decisions)
    logger.info(
        "정규화 완료: %s — %d 그룹 병합, %d개 흡수, registry %d개",
        registry_name,
        group_total,
        absorbed_total,
        len(registry.entries),
    )
    return {
        "groups": group_total,
        "absorbed": absorbed_total,
        "registry": len(registry.entries),
    }


async def run_phase2_5() -> dict:
    """Phase 2.5 entry point — entity alias canonicalization."""
    return await canonicalize("entity", prefix="entity")


async def run_phase3_5() -> dict:
    """Phase 3.5 entry point — concept alias canonicalization."""
    return await canonicalize("concept", prefix="concept")
