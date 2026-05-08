"""Human-readable Korean labels for tool-call streaming events.

The streaming UI used to show the raw tool name and the first argument
(e.g. ``read_with_anchor wiki-output/entities/entity-310.md``). For the
lawyer-facing front-end we resolve those into "{action} - {subject}"
labels backed by the workspace's evidence/registry data:

  * ``read_with_anchor``   → "문서 검토 - {number} : {name}" (sources)
                              / "{name_ko} 엔티티 확인"      (entities)
                              / "{name_ko} 개념 확인"        (concepts)
  * ``smart_search``       → "자료 검색 - {query}"
  * ``list_evidence``      → "증거 목록 - {filter desc}"
  * ``verify_citations``   → "인용 검증 - {path}"
  * ``check_completeness`` → "구조 점검 - {doctype 한국어}"

Tools without a registered action (memory/strategy/todos/task/calculate/
write_file) return ``None`` so the front-end keeps its existing fallback.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from ..workspace import Workspace


# Tool name → Korean verb prefix.
_ACTION_BY_TOOL: dict[str, str] = {
    "read_with_anchor": "문서 검토",
    "smart_search": "자료 검색",
    "list_evidence": "증거 목록",
    "verify_citations": "인용 검증",
    "check_completeness": "구조 점검",
}


# `check_completeness` doctype keys → 한국어 라벨.
_KIND_LABEL: dict[str, str] = {
    "evidence_acknowledgment": "증거인부서",
    "witness_questions": "증인심문사항",
    "defendant_questions": "피고인심문사항",
    "defense_opinion": "변호인 의견서",
    "civil_brief": "민사 준비서면",
    "evidence_pros_cons": "증거 유불리표",
    "timeline": "연표",
    "issues": "쟁점표",
}


_CITATION_RE = re.compile(r"^([^\s#]+)(?:#([^\s]+))?$")
_SOURCE_PATH_RE = re.compile(r"^wiki-output/sources/source-(.+)\.md$")
_ENTITY_PATH_RE = re.compile(r"^wiki-output/entities/(entity-\d+)\.md$")
_CONCEPT_PATH_RE = re.compile(r"^wiki-output/concepts/(concept-\d+)\.md$")
_JSON_PATH_RE = re.compile(r"^json/(.+)\.json$")

_PAGE_ANCHOR_RE = re.compile(r"^p(\d+)(?:\.\.(\d+))?$")
_LINE_ANCHOR_RE = re.compile(r"^L(\d+)(?:-L?(\d+))?$")
_SECTION_ANCHOR_RE = re.compile(r"^sec:(.+)$")


def _format_anchor(anchor: str | None) -> str:
    """Render an anchor as a Korean-friendly subject suffix.

    pN          → " (N쪽)"
    pA..B       → " (A-B쪽)"
    Lstart-Lend → " (L{start}-L{end})"
    sec:slug    → " (§slug)"
    """
    if not anchor:
        return ""
    if m := _PAGE_ANCHOR_RE.match(anchor):
        a, b = m.group(1), m.group(2)
        return f" ({a}-{b}쪽)" if b else f" ({a}쪽)"
    if m := _LINE_ANCHOR_RE.match(anchor):
        a, b = m.group(1), m.group(2)
        return f" (L{a}-L{b})" if b else f" (L{a})"
    if m := _SECTION_ANCHOR_RE.match(anchor):
        return f" (§{m.group(1)})"
    return f" (#{anchor})"


class _CaseLabelIndex:
    """Lazy per-workspace index resolving wiki paths to human names.

    Reads ``cache/entity_registry.json``, ``cache/concept_registry.json``,
    and every ``json/*.json`` document on first access — then caches the
    derived dicts on the instance. One index per build_label_fn() call.
    """

    def __init__(self, ws: Workspace):
        self.ws = ws
        self._entities: dict | None = None
        self._concepts: dict | None = None
        self._sources: dict[str, dict] | None = None

    def _entity_registry(self) -> dict:
        if self._entities is None:
            try:
                raw = json.loads(self.ws.read("cache/entity_registry.json"))
                self._entities = raw.get("entries", {})
            except Exception:
                self._entities = {}
        return self._entities

    def _concept_registry(self) -> dict:
        if self._concepts is None:
            try:
                raw = json.loads(self.ws.read("cache/concept_registry.json"))
                self._concepts = raw.get("entries", {})
            except Exception:
                self._concepts = {}
        return self._concepts

    def _source_index(self) -> dict[str, dict]:
        """Map source key → ``{number, name}``.

        Keys are indexed under both the doc's ``id`` (e.g. ``cdoc_…``) and
        the json-file stem (e.g. ``석명준비명령``) so both
        ``wiki-output/sources/source-{id}.md`` and ``json/{stem}.json``
        forms resolve.
        """
        if self._sources is not None:
            return self._sources
        out: dict[str, dict] = {}
        try:
            json_paths = list(self.ws.glob("json/*.json"))
        except Exception:
            json_paths = []
        for jp in json_paths:
            try:
                doc = json.loads(self.ws.read(jp))
            except Exception:
                continue
            meta = {
                "number": (doc.get("number") or "").strip(),
                "name": (doc.get("name") or doc.get("title") or "").strip(),
            }
            sid = str(doc.get("id") or "").strip()
            if sid:
                out[sid] = meta
            stem = jp.removeprefix("json/").removesuffix(".json")
            out.setdefault(stem, meta)
        self._sources = out
        return out

    def source_label(self, key: str) -> str | None:
        meta = self._source_index().get(key)
        if not meta:
            return None
        number, name = meta.get("number") or "", meta.get("name") or ""
        if number and name and number != name:
            return f"{number} : {name}"
        return name or number or None

    def entity_label(self, eid: str) -> str | None:
        meta = self._entity_registry().get(eid)
        if not meta:
            return None
        return f"{meta.get('name_ko') or eid} 엔티티 확인"

    def concept_label(self, cid: str) -> str | None:
        meta = self._concept_registry().get(cid)
        if not meta:
            return None
        return f"{meta.get('name_ko') or cid} 개념 확인"


def _read_with_anchor_subject(idx: _CaseLabelIndex, citation: str) -> str:
    m = _CITATION_RE.match(citation.strip())
    if not m:
        return citation
    path = m.group(1)
    suffix = _format_anchor(m.group(2))
    if sm := _SOURCE_PATH_RE.match(path):
        return (idx.source_label(sm.group(1)) or sm.group(1)) + suffix
    if em := _ENTITY_PATH_RE.match(path):
        return (idx.entity_label(em.group(1)) or em.group(1)) + suffix
    if cm := _CONCEPT_PATH_RE.match(path):
        return (idx.concept_label(cm.group(1)) or cm.group(1)) + suffix
    if jm := _JSON_PATH_RE.match(path):
        return (idx.source_label(jm.group(1)) or jm.group(1)) + suffix
    return path + suffix


def _list_evidence_subject(args: dict[str, Any]) -> str:
    bits: list[str] = []
    if v := args.get("person"):
        bits.append(f"인물: {v}")
    if v := args.get("category"):
        bits.append(f"분류: {v}")
    if v := args.get("name_contains"):
        bits.append(f"제목: {v}")
    return ", ".join(bits) or "전체"


DisplayLabelFn = Callable[[str, dict[str, Any]], "dict[str, str] | None"]


def build_label_fn(workspace: Workspace) -> DisplayLabelFn:
    """Build a stream-event labeler bound to ``workspace``.

    Returns a function ``(tool_name, tool_input_dict) -> {action, subject}``
    or ``None`` for tools without a registered label. The returned callable
    is process-safe and lazy — registries/json files are read on first
    relevant tool call, then memoized.
    """
    idx = _CaseLabelIndex(workspace)

    def _label(name: str, args: dict[str, Any]) -> dict[str, str] | None:
        action = _ACTION_BY_TOOL.get(name)
        if action is None:
            return None
        try:
            if name == "read_with_anchor":
                subject = _read_with_anchor_subject(idx, str(args.get("citation") or ""))
            elif name == "smart_search":
                subject = str(args.get("query") or "").strip()
            elif name == "list_evidence":
                subject = _list_evidence_subject(args)
            elif name == "verify_citations":
                subject = str(args.get("path") or "")
            elif name == "check_completeness":
                kind = str(args.get("kind") or "")
                subject = _KIND_LABEL.get(kind, kind)
            else:
                return None
        except Exception:
            return None
        if not subject:
            return None
        return {"action": action, "subject": subject}

    return _label


__all__ = ["DisplayLabelFn", "build_label_fn"]
