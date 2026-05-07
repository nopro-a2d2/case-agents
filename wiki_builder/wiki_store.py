"""위키 파일시스템 CRUD"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import frontmatter

from wiki_builder.config import wiki_settings
from wiki_builder.models import CompileResult, Registry, RegistryEntry

logger = logging.getLogger(__name__)

SOURCES_BLOCK_START = "<!-- AUTO_SOURCES_START -->"
SOURCES_BLOCK_END = "<!-- AUTO_SOURCES_END -->"
RAW_BLOCK_START = "<!-- AUTO_RAW_START -->"
RAW_BLOCK_END = "<!-- AUTO_RAW_END -->"
SYNTHESIS_BLOCK_START = "<!-- AUTO_SYNTHESIS_START -->"
SYNTHESIS_BLOCK_END = "<!-- AUTO_SYNTHESIS_END -->"

_SOURCES_BLOCK_RE = re.compile(
    rf"\n*{re.escape(SOURCES_BLOCK_START)}.*?{re.escape(SOURCES_BLOCK_END)}\n*",
    re.DOTALL,
)
_RAW_BLOCK_RE = re.compile(
    rf"{re.escape(RAW_BLOCK_START)}\s*(.*?)\s*{re.escape(RAW_BLOCK_END)}", re.DOTALL
)
_SYNTH_BLOCK_RE = re.compile(
    rf"{re.escape(SYNTHESIS_BLOCK_START)}\s*(.*?)\s*{re.escape(SYNTHESIS_BLOCK_END)}",
    re.DOTALL,
)
_RAW_SOURCE_HEADING_RE = re.compile(r"^### source-(\S+)\s*$", re.MULTILINE)
_RAW_SUBSECTION_RE = re.compile(
    r"^### source-(\S+)\s*\n(.*?)(?=^### source-|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _cite(doc_id: str, pages: list[int]) -> str:
    """단일 인용 토큰 (source-{doc_id}:p1,p2,...) 또는 (source-{doc_id})"""
    if not pages:
        return f"(source-{doc_id})"
    return f"(source-{doc_id}:{','.join(str(p) for p in pages)})"


def _strip_sources_block(body: str) -> str:
    """본문에서 sentinel로 둘러싼 '## 출처' 블록을 제거"""
    return _SOURCES_BLOCK_RE.sub("\n", body).rstrip()


def _render_sources_block(entry: RegistryEntry) -> str:
    """entry.source_page_map을 sentinel 블록으로 렌더링. 비어 있으면 빈 문자열."""
    if not entry.source_ids:
        return ""

    lines = [SOURCES_BLOCK_START, "## 출처"]
    for source_id in entry.source_ids:
        pages = entry.source_page_map.get(source_id, [])
        # source_id 형식: "source-885" 또는 "885" — 정규화하여 link 텍스트 생성
        sid = source_id if source_id.startswith("source-") else f"source-{source_id}"
        doc_id = sid.removeprefix("source-")
        token = _cite(doc_id, pages)
        lines.append(f"- [[sources/{sid}.md|{sid}]] {token}")
    lines.append(SOURCES_BLOCK_END)
    return "\n".join(lines)


def wiki_dir() -> Path:
    return wiki_settings.WIKI_OUTPUT_DIR


def ensure_dirs() -> None:
    """위키 출력 디렉토리 생성"""
    for sub in ("sources", "entities", "concepts"):
        (wiki_dir() / sub).mkdir(parents=True, exist_ok=True)


def _format_failure(vf: dict) -> str:
    """검증 실패 fact 한 건을 마크다운 한 줄로 포맷."""
    cat = vf.get("category", "?")
    fld = vf.get("field", {})
    if cat == "date":
        label = f"{fld.get('date', '')} — {fld.get('event', '')}"
    elif cat == "amount":
        label = f"{fld.get('amount', '')} — {fld.get('context', '')}"
    elif cat in ("person", "organization"):
        label = f"{fld.get('name', '')} ({fld.get('role', '')})"
    elif cat == "legal_provision":
        label = fld.get("text", "")
    elif cat == "detailed":
        text = fld.get("text", "")
        label = text[:200] + ("…" if len(text) > 200 else "")
    else:
        label = str(fld)
    pages = fld.get("pages") or []
    pages_suffix = f" (인용 p.{','.join(str(p) for p in pages)})" if pages else ""
    return f"- **[{cat}]** {label}{pages_suffix}"


def write_source_page(
    doc_id: str,
    title: str,
    category: str,
    person: str | None,
    pages: int,
    tokens: int,
    result: CompileResult,
) -> Path:
    """소스 페이지 마크다운 파일 생성"""
    metadata = {
        "id": doc_id,
        "title": title,
        "type": "source",
        "category": category,
        "person": person,
        "pages": pages,
        "tokens": tokens,
        "compiled_at": datetime.now().isoformat(),
        "verified": not bool(result.verification_failures),
    }

    body_parts = [
        f"# {title}",
        "",
        "## 요약",
        result.summary,
        "",
        "## 핵심 사실",
    ]

    if result.key_facts.dates:
        body_parts.append("### 날짜")
        for d in result.key_facts.dates:
            body_parts.append(f"- **{d.date}**: {d.event} {_cite(doc_id, d.pages)}")

    if result.key_facts.amounts:
        body_parts.append("### 금액")
        for a in result.key_facts.amounts:
            body_parts.append(f"- **{a.amount}**: {a.context} {_cite(doc_id, a.pages)}")

    if result.key_facts.persons:
        body_parts.append("### 인물")
        for p in result.key_facts.persons:
            body_parts.append(f"- **{p.name}**: {p.role} {_cite(doc_id, p.pages)}")

    if result.key_facts.organizations:
        body_parts.append("### 조직")
        for o in result.key_facts.organizations:
            body_parts.append(f"- **{o.name}**: {o.role} {_cite(doc_id, o.pages)}")

    if result.key_facts.legal_provisions:
        body_parts.append("### 법적 조항")
        for lp in result.key_facts.legal_provisions:
            body_parts.append(f"- {lp}")

    body_parts.extend(["", "## 상세 내용"])
    for s in result.detailed_content:
        body_parts.append(f"- {s.text} {_cite(doc_id, s.pages)}")

    if result.entities:
        body_parts.extend(["", "## 관련 엔티티"])
        for e in result.entities:
            body_parts.append(f"- {e.name_ko} ({e.type})")

    if result.concepts:
        body_parts.extend(["", "## 관련 개념"])
        for c in result.concepts:
            body_parts.append(f"- {c.name_ko}: {c.description}")

    if result.verification_failures:
        body_parts.extend(
            [
                "",
                "## 검증 실패 (수동 확인 필요)",
                f"_Phase 1.5 string-level back-check 에서 인용 페이지에 매칭되지 않은 fact {len(result.verification_failures)}건._",
            ]
        )
        for vf in result.verification_failures:
            body_parts.append(_format_failure(vf))

    content = "\n".join(body_parts)
    post = frontmatter.Post(content, **metadata)
    path = wiki_dir() / "sources" / f"source-{doc_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def _extract_raw(body: str) -> str:
    m = _RAW_BLOCK_RE.search(body)
    return m.group(1).strip() if m else ""


def _extract_synth(body: str) -> str:
    m = _SYNTH_BLOCK_RE.search(body)
    return m.group(1).strip() if m else ""


def _existing_source_ids_in_raw(raw: str) -> set[str]:
    return set(_RAW_SOURCE_HEADING_RE.findall(raw))


def _wrap_raw(raw_content: str) -> str:
    raw_content = raw_content.strip()
    if not raw_content:
        body = "## 출처별 사실\n\n_(아직 누적된 사실 없음)_"
    elif not raw_content.startswith("## "):
        body = "## 출처별 사실\n\n" + raw_content
    else:
        body = raw_content
    return f"{RAW_BLOCK_START}\n{body}\n{RAW_BLOCK_END}"


def _wrap_synthesis(synth_content: str) -> str:
    body = synth_content.strip() or "_(아직 합성 미실행)_"
    if not body.lstrip().startswith("## "):
        body = "## 종합\n\n" + body
    return f"{SYNTHESIS_BLOCK_START}\n{body}\n{SYNTHESIS_BLOCK_END}"


def _compose_managed_body(entry: RegistryEntry, raw: str, synth: str) -> str:
    """엔티티/개념 페이지 본문 = title + RAW + SYNTHESIS + SOURCES (sentinel 기반)."""
    title = f"# {entry.name_ko}"
    sources = _render_sources_block(entry)
    parts = [title, "", _wrap_raw(raw), "", _wrap_synthesis(synth)]
    if sources:
        parts.extend(["", sources])
    return "\n".join(parts) + "\n"


def _build_managed_metadata(entry: RegistryEntry, *, is_concept: bool) -> dict:
    md: dict = {
        "type": "concept" if is_concept else "entity",
        "name_ko": entry.name_ko,
        "aliases": entry.aliases,
        "source_count": len(entry.source_ids),
        "sources": entry.source_page_map,
        "updated_at": datetime.now().isoformat(),
    }
    if not is_concept:
        md["entity_type"] = entry.type
    return md


def _write_managed_page(
    entry: RegistryEntry, content: str, *, is_concept: bool
) -> Path:
    metadata = _build_managed_metadata(entry, is_concept=is_concept)
    post = frontmatter.Post(content, **metadata)
    path = wiki_dir() / entry.file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def append_managed_raw_subsection(
    entry: RegistryEntry,
    source_id: str,
    chunk_lines: str,
    *,
    is_concept: bool = False,
) -> Path:
    """엔티티/개념 RAW 섹션에 ``### source-N`` 서브섹션을 append. 멱등성 보장."""
    path = wiki_dir() / entry.file
    raw = ""
    synth = ""
    if path.exists():
        _, body = read_page(path)
        raw = _extract_raw(body)
        synth = _extract_synth(body)

    if source_id not in _existing_source_ids_in_raw(raw):
        new_subsection = f"### source-{source_id}\n{chunk_lines.strip()}"
        raw = (raw.rstrip() + "\n\n" + new_subsection) if raw else (
            "## 출처별 사실\n\n" + new_subsection
        )

    body = _compose_managed_body(entry, raw, synth)
    return _write_managed_page(entry, body, is_concept=is_concept)


def set_managed_synthesis(
    entry: RegistryEntry,
    synthesis_body: str,
    *,
    is_concept: bool = False,
) -> Path:
    """SYNTHESIS 섹션만 갱신. RAW 는 보존."""
    path = wiki_dir() / entry.file
    raw = ""
    if path.exists():
        _, body = read_page(path)
        raw = _extract_raw(body)
    new_body = _compose_managed_body(entry, raw, synthesis_body)
    return _write_managed_page(entry, new_body, is_concept=is_concept)


def merge_raw_subsections_from_body(
    target_entry: RegistryEntry,
    source_body: str,
    *,
    is_concept: bool = False,
) -> Path | None:
    """다른 페이지 body 에서 RAW source 서브섹션들을 추출해 target 의 RAW 로 병합 (멱등)."""
    source_raw = _extract_raw(source_body)
    if not source_raw:
        return None
    last_path: Path | None = None
    for m in _RAW_SUBSECTION_RE.finditer(source_raw):
        sid = m.group(1)
        chunk = m.group(2).strip()
        last_path = append_managed_raw_subsection(
            target_entry, sid, chunk, is_concept=is_concept
        )
    return last_path


def write_entity_page(entry: RegistryEntry, body: str | None = None) -> Path:
    """[backward-compat] entity 페이지 재작성. body 인자는 무시 — 새 구조에서는 RAW append 와 SYNTHESIS 갱신을 분리해서 사용."""
    path = wiki_dir() / entry.file
    raw = ""
    synth = ""
    if path.exists():
        _, existing = read_page(path)
        raw = _extract_raw(existing)
        synth = _extract_synth(existing)
    return _write_managed_page(
        entry, _compose_managed_body(entry, raw, synth), is_concept=False
    )


def write_concept_page(entry: RegistryEntry, body: str | None = None) -> Path:
    """[backward-compat] concept 페이지 재작성. body 인자 무시."""
    path = wiki_dir() / entry.file
    raw = ""
    synth = ""
    if path.exists():
        _, existing = read_page(path)
        raw = _extract_raw(existing)
        synth = _extract_synth(existing)
    return _write_managed_page(
        entry, _compose_managed_body(entry, raw, synth), is_concept=True
    )


def read_page(path: Path) -> tuple[dict, str]:
    """위키 페이지 읽기 → (metadata, body)"""
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


def save_registry(registry: Registry, name: str) -> None:
    """레지스트리를 캐시에 저장"""
    path = wiki_settings.CACHE_DIR / f"{name}_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(registry.model_dump_json(indent=2), encoding="utf-8")


def load_registry(name: str, prefix: str) -> Registry:
    """캐시에서 레지스트리 로드"""
    path = wiki_settings.CACHE_DIR / f"{name}_registry.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return Registry(**data)
    return Registry(prefix=prefix)


def append_log(message: str) -> None:
    """log.md에 기록 추가"""
    log_path = wiki_dir() / "log.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"- [{timestamp}] {message}\n"
    if not log_path.exists():
        log_path.write_text("# 위키 컴파일 로그\n\n", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)
