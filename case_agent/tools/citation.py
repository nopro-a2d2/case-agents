"""Citation primitives.

Citation grammar (single canonical form used everywhere):

    @@[id]

``id`` is the value of the top-level ``"id"`` field in the source evidence
JSON file (under ``json/<file>.json``). Examples:

    @@[1]
    @@[cdoc_01KKH4TTAG000000000000000S]

There are no page/line/section anchors in the citation token itself. When the
agent needs a specific page, line range, or wiki-md section, it passes them as
**arguments to** ``read_evidence`` — they are NOT embedded in the citation
that appears in artifacts/briefs.

``read_evidence`` reads a region of an evidence document keyed by ``id``
plus optional page/line/section parameters. It returns the snippet plus the
canonical ``@@[id]`` citation the agent can paste verbatim.

``list_evidence`` enumerates all evidence (json source files) with metadata.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from case_agent.workspace import Workspace

# ---------------------------------------------------------------------------
# Citation parsing
# ---------------------------------------------------------------------------


CITE_RE = re.compile(r"^@@\[(?P<id>[^\]\s]+)\]$")


@dataclass(slots=True)
class Citation:
    id: str

    def __str__(self) -> str:
        return f"@@[{self.id}]"


def parse_citation(s: str) -> Citation:
    m = CITE_RE.match(s.strip())
    if not m:
        raise ValueError(f"not a citation: {s!r}")
    return Citation(id=m.group("id"))


# ---------------------------------------------------------------------------
# id registry
# ---------------------------------------------------------------------------


_REGISTRY_ATTR = "_id_registry"


def build_id_registry(ws: Workspace) -> dict[str, str]:
    """Return ``{id: json_path}`` over every ``json/*.json`` evidence file.

    Cached on the workspace instance after the first call. Raises on duplicate
    ids (corrupt case data) so the agent fails fast rather than citing the
    wrong document.
    """
    cached = getattr(ws, _REGISTRY_ATTR, None)
    if cached is not None:
        return cached
    out: dict[str, str] = {}
    for jp in ws.glob("json/*.json"):
        try:
            doc = json.loads(ws.read(jp))
        except Exception:
            continue
        raw = doc.get("id")
        if raw in (None, ""):
            continue
        did = str(raw)
        if did in out and out[did] != jp:
            raise ValueError(
                f"duplicate id {did!r}: {out[did]} and {jp}"
            )
        out[did] = jp
    try:
        setattr(ws, _REGISTRY_ATTR, out)
    except (AttributeError, TypeError):
        pass
    return out


def resolve_id(ws: Workspace, id: str) -> str:
    """Return the workspace-relative json path for ``id``."""
    reg = build_id_registry(ws)
    if id not in reg:
        raise KeyError(f"unknown id: {id!r}")
    return reg[id]


# ---------------------------------------------------------------------------
# Heading slug for wiki anchors (still used by read_evidence section= param)
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
# read_evidence
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvidenceRead:
    citation: str  # canonical `@@[id]`
    id: str
    json_path: str
    snippet: str
    kind: str  # "page" | "lines" | "section" | "full"

    def to_dict(self) -> dict:
        return {
            "citation": self.citation,
            "id": self.id,
            "json_path": self.json_path,
            "snippet": self.snippet,
            "kind": self.kind,
        }


def read_evidence(
    ws: Workspace,
    id: str,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    section_id: str | None = None,
    max_chars: int = 4000,
) -> EvidenceRead:
    """Read a region of an evidence document keyed by ``id``.

    Exactly one of the following addressing modes may be used per call:
      * ``start_page`` (with optional ``end_page``) — read by page in json source.
      * ``start_line`` (with optional ``end_line``) — read by line range.
      * ``section_id`` — wiki-md heading slug (e.g. ``"1-개념-정의"``).
      * None of the above — return the full json ``content`` body.
    """
    json_path = resolve_id(ws, id)
    addressing_modes = sum(
        x is not None
        for x in (start_page, start_line, section_id)
    )
    if addressing_modes > 1:
        raise ValueError(
            "specify at most one of start_page / start_line / section_id"
        )

    if start_page is not None:
        if end_page is None:
            end_page = start_page
        if start_page > end_page:
            raise ValueError(
                f"invalid page range: {start_page}..{end_page} (start > end)"
            )
        doc = json.loads(ws.read(json_path))
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
                raise ValueError(f"page {start_page} not found in {json_path}")
            raise ValueError(
                f"page range {start_page}..{end_page} not found in {json_path}"
            )
        snippet = "\n\n".join(parts)
        return EvidenceRead(
            citation=f"@@[{id}]",
            id=id,
            json_path=json_path,
            snippet=snippet[:max_chars],
            kind="page",
        )

    if start_line is not None:
        if end_line is None:
            end_line = start_line
        text = ws.read(json_path, range=(start_line, end_line))
        return EvidenceRead(
            citation=f"@@[{id}]",
            id=id,
            json_path=json_path,
            snippet=text[:max_chars],
            kind="lines",
        )

    if section_id is not None:
        text = ws.read(json_path)
        slugs = _md_heading_slugs(text)
        if section_id not in slugs:
            raise ValueError(f"section slug {section_id!r} not found in {json_path}")
        s, e = slugs[section_id]
        snippet = "\n".join(text.splitlines()[s - 1 : e])
        return EvidenceRead(
            citation=f"@@[{id}]",
            id=id,
            json_path=json_path,
            snippet=snippet[:max_chars],
            kind="section",
        )

    # full document fallback — read whole json content
    doc = json.loads(ws.read(json_path))
    content = doc.get("content")
    if isinstance(content, list):
        snippet = "\n".join(str(blk.get("text", "")) for blk in content)
    else:
        snippet = str(content or "")
    return EvidenceRead(
        citation=f"@@[{id}]",
        id=id,
        json_path=json_path,
        snippet=snippet[:max_chars],
        kind="full",
    )


# ---------------------------------------------------------------------------
# list_evidence
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvidenceItem:
    id: str
    title: str
    number: str | None         # e.g. "갑 제3호증" if present
    category: str | None
    person: str | None
    pages: int | None
    json_path: str
    wiki_path: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "number": self.number,
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
        did = str(doc.get("id", ""))
        title = str(doc.get("name", "") or doc.get("title", ""))
        number = doc.get("number")
        cat = doc.get("category")
        pers = doc.get("person")
        pages = doc.get("total_page")
        if person and pers != person:
            continue
        if category and cat != category:
            continue
        if name_contains and name_contains not in title:
            continue
        wiki = f"wiki-output/sources/source-{did}.md"
        out.append(
            EvidenceItem(
                id=did,
                title=title,
                number=number if number else None,
                category=cat,
                person=pers,
                pages=int(pages) if pages is not None else None,
                json_path=jp,
                wiki_path=wiki if ws.exists(wiki) else None,
            )
        )
    return out
