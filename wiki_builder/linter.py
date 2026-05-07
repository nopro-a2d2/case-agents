"""Phase 6: 위키 품질 검증 (린트)

- 고아 페이지: 어디서도 참조되지 않는 entity/concept
- 깨진 링크: 존재하지 않는 페이지 참조
- 모순 탐지: (선택적) LLM 기반
"""

import logging
import re
from datetime import datetime

import frontmatter

from wiki_builder.wiki_store import wiki_dir

logger = logging.getLogger(__name__)


def _collect_all_pages() -> dict[str, tuple[dict, str]]:
    """모든 위키 페이지 수집 → {rel_path: (meta, body)}"""
    pages: dict[str, tuple[dict, str]] = {}
    wdir = wiki_dir()
    for subdir in ("sources", "entities", "concepts"):
        d = wdir / subdir
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            rel = str(path.relative_to(wdir))
            post = frontmatter.load(str(path))
            pages[rel] = (dict(post.metadata), post.content)
    return pages


def _extract_wikilinks(body: str) -> list[str]:
    """본문에서 [[path|label]] 또는 [[path]] 형태의 링크 추출"""
    pattern = r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    return re.findall(pattern, body)


def find_orphan_pages(pages: dict[str, tuple[dict, str]]) -> list[str]:
    """어디서도 참조되지 않는 entity/concept 페이지"""
    referenced: set[str] = set()
    for _, (_, body) in pages.items():
        for link_target in _extract_wikilinks(body):
            referenced.add(link_target)

    orphans = []
    for rel_path in pages:
        if rel_path.startswith("sources/"):
            continue  # source는 참조 안 돼도 OK
        if rel_path not in referenced:
            orphans.append(rel_path)

    return orphans


def find_broken_links(pages: dict[str, tuple[dict, str]]) -> list[tuple[str, str]]:
    """존재하지 않는 페이지를 참조하는 링크"""
    all_paths = set(pages.keys())
    broken: list[tuple[str, str]] = []

    for rel_path, (_, body) in pages.items():
        for link_target in _extract_wikilinks(body):
            if link_target not in all_paths:
                broken.append((rel_path, link_target))

    return broken


def count_stats(pages: dict[str, tuple[dict, str]]) -> dict:
    """위키 통계"""
    source_count = sum(1 for p in pages if p.startswith("sources/"))
    entity_count = sum(1 for p in pages if p.startswith("entities/"))
    concept_count = sum(1 for p in pages if p.startswith("concepts/"))

    total_links = 0
    for _, (_, body) in pages.items():
        total_links += len(_extract_wikilinks(body))

    total_chars = sum(len(body) for _, (_, body) in pages.items())

    return {
        "total_pages": len(pages),
        "sources": source_count,
        "entities": entity_count,
        "concepts": concept_count,
        "total_wikilinks": total_links,
        "total_chars": total_chars,
    }


def run_phase6() -> str:
    """Phase 6: 린트 실행

    Returns:
        린트 리포트 마크다운
    """
    pages = _collect_all_pages()
    stats = count_stats(pages)
    orphans = find_orphan_pages(pages)
    broken = find_broken_links(pages)

    # 리포트 생성
    lines = [
        "# 위키 린트 리포트",
        "",
        f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 통계",
        f"- 총 페이지: {stats['total_pages']}",
        f"  - 소스: {stats['sources']}",
        f"  - 엔티티: {stats['entities']}",
        f"  - 개념: {stats['concepts']}",
        f"- 총 wikilink: {stats['total_wikilinks']}",
        f"- 총 문자 수: {stats['total_chars']:,}",
        "",
    ]

    # 고아 페이지
    lines.append(f"## 고아 페이지 ({len(orphans)}개)")
    if orphans:
        for o in orphans:
            lines.append(f"- {o}")
    else:
        lines.append("없음")
    lines.append("")

    # 깨진 링크
    lines.append(f"## 깨진 링크 ({len(broken)}개)")
    if broken:
        for src, target in broken:
            lines.append(f"- `{src}` → `{target}`")
    else:
        lines.append("없음")
    lines.append("")

    report = "\n".join(lines)

    # 파일 저장
    report_path = wiki_dir() / "lint_report.md"
    report_path.write_text(report, encoding="utf-8")

    logger.info(
        "린트 완료: 페이지 %d, 고아 %d, 깨진 링크 %d",
        stats["total_pages"],
        len(orphans),
        len(broken),
    )
    return report
