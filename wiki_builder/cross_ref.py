"""Phase 4: 교차 참조 [[wikilink]] 자동 삽입

모든 위키 페이지를 스캔하여 엔티티/개념 이름이 본문에 등장하면
자동으로 [[wikilink]] 링크를 삽입합니다.

멱등성 보장: sanitize → strip → insert 순서로 실행.
"""

import logging
import re

import frontmatter

from wiki_builder.models import Registry
from wiki_builder.wiki_store import (
    SOURCES_BLOCK_END,
    SOURCES_BLOCK_START,
    load_registry,
    wiki_dir,
)

logger = logging.getLogger(__name__)

_WIKILINK_WITH_LABEL = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
_WIKILINK_SIMPLE = re.compile(r"\[\[([^\]|]+)\]\]")
_WIKILINK_ANY = re.compile(r"\[\[[^\]]+\]\]")
_SOURCES_BLOCK_PROTECT_RE = re.compile(
    rf"{re.escape(SOURCES_BLOCK_START)}.*?{re.escape(SOURCES_BLOCK_END)}",
    re.DOTALL,
)


def _protect_sources_block(text: str) -> tuple[str, list[str]]:
    """sentinel '## 출처' 블록을 placeholder로 마스킹. 반환된 list는 복원에 사용."""
    blocks: list[str] = []

    def _mask(m: re.Match) -> str:
        blocks.append(m.group(0))
        return f"\x00SRCBLK{len(blocks) - 1}\x00"

    return _SOURCES_BLOCK_PROTECT_RE.sub(_mask, text), blocks


def _restore_sources_block(text: str, blocks: list[str]) -> str:
    for i, b in enumerate(blocks):
        text = text.replace(f"\x00SRCBLK{i}\x00", b)
    return text


def sanitize_wiki_pages() -> int:
    """삼중 괄호 등 malformed wikilink 정리 (pre-pass)

    LLM이 생성한 [[[...]]] 삼중 괄호를 [[...]]로 정규화.

    Returns:
        수정된 페이지 수
    """
    wdir = wiki_dir()
    fixed = 0
    for subdir in ("sources", "entities", "concepts"):
        d = wdir / subdir
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            new_text = text.replace("[[[", "[[").replace("]]]", "]]")
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                fixed += 1
    logger.info("Sanitize 완료: %d개 페이지 수정", fixed)
    return fixed


def strip_all_wikilinks() -> int:
    """모든 페이지에서 [[...]] 링크를 plain text로 복원 (멱등성 보장)

    [[path|label]] → label, [[path]] → path 로 변환.
    단 sentinel '## 출처' 블록은 보존(매 빌드 wiki_store가 재생성).

    Returns:
        수정된 페이지 수
    """
    wdir = wiki_dir()
    stripped = 0
    for subdir in ("sources", "entities", "concepts"):
        d = wdir / subdir
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            post = frontmatter.load(str(path))
            original = post.content
            masked, blocks = _protect_sources_block(original)
            updated = _WIKILINK_WITH_LABEL.sub(r"\2", masked)
            updated = _WIKILINK_SIMPLE.sub(r"\1", updated)
            updated = _restore_sources_block(updated, blocks)
            if updated != original:
                post.content = updated
                path.write_text(frontmatter.dumps(post), encoding="utf-8")
                stripped += 1
    logger.info("Strip 완료: %d개 페이지에서 wikilink 제거", stripped)
    return stripped


def _build_name_to_link(entity_registry: Registry, concept_registry: Registry) -> dict[str, str]:
    """이름 → wikilink 매핑 구축 (긴 이름 우선)"""
    mapping: dict[str, str] = {}

    for entry in entity_registry.entries.values():
        link = f"[[{entry.file}|{entry.name_ko}]]"
        mapping[entry.name_ko] = link
        for alias in entry.aliases:
            mapping[alias] = link

    for entry in concept_registry.entries.values():
        link = f"[[{entry.file}|{entry.name_ko}]]"
        mapping[entry.name_ko] = link
        for alias in entry.aliases:
            mapping[alias] = link

    return mapping


def _insert_links(body: str, name_to_link: dict[str, str]) -> str:
    """본문에 [[wikilink]] 삽입

    이미 링크된 span은 플레이스홀더로 마스킹하여 보호하고,
    나머지 영역에서만 치환합니다. 제목(#) 줄은 건드리지 않습니다.
    긴 이름부터 치환하여 부분 매칭 문제 방지.
    """
    sorted_names = sorted(name_to_link.keys(), key=len, reverse=True)

    for name in sorted_names:
        if len(name) < 2:
            continue
        link = name_to_link[name]
        lines = body.split("\n")
        new_lines = []
        for line in lines:
            if line.startswith("#"):
                new_lines.append(line)
                continue
            # 이미 삽입된 [[...]] span을 플레이스홀더로 마스킹
            placeholders: list[str] = []

            def _mask(m: re.Match) -> str:
                placeholders.append(m.group(0))
                return f"\x00WL{len(placeholders) - 1}\x00"

            masked = _WIKILINK_ANY.sub(_mask, line)
            # 마스킹된 영역 외에서 첫 번째 매칭만 치환
            if name in masked:
                masked = masked.replace(name, link, 1)
            # 플레이스홀더 복원
            for i, ph in enumerate(placeholders):
                masked = masked.replace(f"\x00WL{i}\x00", ph)
            new_lines.append(masked)
        body = "\n".join(new_lines)

    return body


def run_phase4() -> int:
    """Phase 4: 교차 참조 자동 삽입

    Returns:
        수정된 페이지 수
    """
    entity_registry = load_registry("entity", prefix="entity")
    concept_registry = load_registry("concept", prefix="concept")

    name_to_link = _build_name_to_link(entity_registry, concept_registry)
    logger.info("교차 참조 매핑: %d개 이름", len(name_to_link))

    modified = 0
    wdir = wiki_dir()

    for subdir in ("sources", "entities", "concepts"):
        d = wdir / subdir
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            post = frontmatter.load(str(path))
            original = post.content
            masked, blocks = _protect_sources_block(original)
            updated = _insert_links(masked, name_to_link)
            updated = _restore_sources_block(updated, blocks)

            if updated != original:
                post.content = updated
                path.write_text(frontmatter.dumps(post), encoding="utf-8")
                modified += 1

    logger.info("Phase 4 완료: %d개 페이지에 교차 참조 삽입", modified)
    return modified
