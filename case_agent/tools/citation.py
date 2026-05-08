"""Citation primitives.

Citation grammar (single canonical form used everywhere):

    {workspace_path}#{anchor}

where anchor is one of:
    L<a>-<b>          line range, 1-based inclusive  (txt files)
    p<n>              page number                    (json source files)
    p<a>..<b>         page range, inclusive          (json source files)
    sec:<heading-id>  markdown heading slug          (wiki md files)

Examples:
    json/1.json#p2
    json/1.json#p1..5
    sources/공소장.txt#L120-L145
    wiki-output/concepts/concept-002.md#sec:1-개념-정의

`read_with_anchor` reads a file region keyed by an anchor and returns both
the snippet and a normalized citation string (so the agent can paste it back
into artifacts/drafts verbatim and `verify_citations` will accept it).

`list_evidence` enumerates all evidence (json source files) with metadata.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from ..workspace import Workspace


# ---------------------------------------------------------------------------
# Anchor parsing
# ---------------------------------------------------------------------------


CITE_RE = re.compile(r"^(?P<path>[^\s#]+)#(?P<anchor>\S+)$")
LINE_RE = re.compile(r"^L(?P<start>\d+)(?:-L?(?P<end>\d+))?$")
PAGE_RE = re.compile(r"^p(?P<start>\d+)(?:\.\.(?P<end>\d+))?$")
SEC_RE = re.compile(r"^sec:(?P<slug>.+)$")


@dataclass(slots=True)
class Citation:
    path: str
    anchor: str

    def __str__(self) -> str:  # noqa: DUNDER
        return f"{self.path}#{self.anchor}"


def parse_citation(s: str) -> Citation:
    m = CITE_RE.match(s.strip())
    if not m:
        raise ValueError(f"not a citation: {s!r}")
    return Citation(path=m.group("path"), anchor=m.group("anchor"))


# ---------------------------------------------------------------------------
# Heading slug for wiki anchors
# ---------------------------------------------------------------------------


_SLUG_STRIP_RE = re.compile(r"[^\w가-힣\- ]+")


def _slugify_heading(heading: str) -> str:
    s = heading.strip().lower()
    s = _SLUG_STRIP_RE.sub("", s)
    s = re.sub(r"\s+", "-", s)
    return s.strip("-")


def _md_heading_slugs(md_text: str) -> dict[str, tuple[int, int]]:
    """Map heading slug -> (start_line, end_line) within the md."""
    lines = md_text.splitlines()
    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        m = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if m:
            headings.append((i, _slugify_heading(m.group(1))))
    out: dict[str, tuple[int, int]] = {}
    for idx, (start, slug) in enumerate(headings):
        end = headings[idx + 1][0] - 1 if idx + 1 < len(headings) else len(lines)
        out[slug] = (start, end)
    return out


# ---------------------------------------------------------------------------
# read_with_anchor
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AnchorRead:
    citation: str
    snippet: str
    kind: str  # "lines" | "page" | "section"

    def to_dict(self) -> dict:
        return {"citation": self.citation, "snippet": self.snippet, "kind": self.kind}


def read_with_anchor(ws: Workspace, citation: str, *, max_chars: int = 4000) -> AnchorRead:
    """Read a region of a workspace file keyed by anchor."""
    cit = parse_citation(citation)
    path = cit.path
    anchor = cit.anchor

    if (m := LINE_RE.match(anchor)):
        start = int(m.group("start"))
        end = int(m.group("end") or m.group("start"))
        text = ws.read(path, range=(start, end))
        return AnchorRead(citation=str(cit), snippet=text[:max_chars], kind="lines")

    if (m := PAGE_RE.match(anchor)):
        if not path.endswith(".json"):
            raise ValueError(f"page anchor only valid on .json files, not {path}")
        start_page = int(m.group("start"))
        end_page = int(m.group("end")) if m.group("end") else start_page
        if start_page > end_page:
            raise ValueError(
                f"invalid page range: p{start_page}..{end_page} (start > end)"
            )
        doc = json.loads(ws.read(path))
        parts: list[str] = []
        last_page: int | None = None
        for blk in doc.get("content", []):
            page = int(blk.get("page", -1))
            if start_page <= page <= end_page:
                if page != last_page:
                    parts.append(f"--- p{page} ---")
                    last_page = page
                parts.append(str(blk.get("text", "")))
        if not parts:
            if start_page == end_page:
                raise ValueError(f"page {start_page} not found in {path}")
            raise ValueError(
                f"page range {start_page}..{end_page} not found in {path}"
            )
        norm_anchor = f"p{start_page}" if start_page == end_page else f"p{start_page}..{end_page}"
        norm_cit = Citation(path=path, anchor=norm_anchor)
        snippet = "\n\n".join(parts)
        return AnchorRead(citation=str(norm_cit), snippet=snippet[:max_chars], kind="page")

    if (m := SEC_RE.match(anchor)):
        slug = m.group("slug").strip()
        text = ws.read(path)
        slugs = _md_heading_slugs(text)
        if slug not in slugs:
            raise ValueError(f"section slug {slug!r} not found in {path}")
        start, end = slugs[slug]
        snippet = "\n".join(text.splitlines()[start - 1 : end])
        return AnchorRead(citation=str(cit), snippet=snippet[:max_chars], kind="section")

    raise ValueError(
        f"unsupported anchor: {anchor!r}. "
        f"Valid forms: Lstart-Lend | pN | pA..B | sec:slug"
    )


# ---------------------------------------------------------------------------
# list_evidence
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvidenceItem:
    source_id: str            # "1", "공소장", ...
    title: str
    category: str | None
    person: str | None
    pages: int | None
    json_path: str            # "json/1.json"
    wiki_path: str | None     # "wiki-output/sources/source-1.md" if it exists

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "category": self.category,
            "person": self.person,
            "pages": self.pages,
            "json_path": self.json_path,
            "wiki_path": self.wiki_path,
        }


def list_evidence(
    ws: Workspace,
    *,
    person: str | None = None,
    category: str | None = None,
    name_contains: str | None = None,
    limit: int = 200,
) -> list[EvidenceItem]:
    """Enumerate evidence files (json/) with optional filters."""
    out: list[EvidenceItem] = []
    for jp in ws.glob("json/*.json"):
        if len(out) >= limit:
            break
        try:
            doc = json.loads(ws.read(jp))
        except Exception:
            continue
        sid = str(doc.get("id", ""))
        title = str(doc.get("name", "") or doc.get("title", ""))
        cat = doc.get("category")
        pers = doc.get("person")
        pages = doc.get("total_page")
        if person and pers != person:
            continue
        if category and cat != category:
            continue
        if name_contains and name_contains not in title:
            continue
        wiki = f"wiki-output/sources/source-{sid}.md"
        out.append(
            EvidenceItem(
                source_id=sid,
                title=title,
                category=cat,
                person=pers,
                pages=int(pages) if pages is not None else None,
                json_path=jp,
                wiki_path=wiki if ws.exists(wiki) else None,
            )
        )
    return out
