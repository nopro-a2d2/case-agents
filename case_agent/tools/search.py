"""smart_search — wiki → cache → (1-hop KG) → json → sources.

This module is the *single* lookup entry-point for both the main agent and the
explore sub-agent. It enforces the lookup priority and 1-hop knowledge-graph
expansion described in the project plan.

Embeddings on disk:
    {case}/cache/embeddings/index.json     # list[{file,id,name_ko,type}]  (row order)
    {case}/cache/embeddings/vectors.npy    # (N, 768) float32
    {case}/cache/embeddings/manifest.json  # {model, dim, files: {path: sha1}}

Registries:
    {case}/cache/concept_registry.json     # {entries: {id: {file, source_ids, ...}}}
    {case}/cache/entity_registry.json      # same shape

Wiki md files use double-bracket links: `[[concepts/concept-001.md|name]]`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Callable, Iterable, Protocol

import numpy as np

from case_agent.workspace import Workspace

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class Embedder(Protocol):
    """Anything that can turn a query string into a 768-d float vector."""

    def embed(self, text: str) -> np.ndarray: ...


@dataclass(slots=True)
class Hit:
    path: str            # workspace-relative md path (e.g. "wiki-output/concepts/concept-002.md")
    score: float         # cosine similarity in [-1, 1]
    id: str              # registry id (concept-002 / entity-001 / source-30)
    name: str            # human name from the index
    type: str            # "entity" | "concept" | "source"
    edge: str | None = None    # "seed" | "link" | "concept" | "entity"
    via: str | None = None     # for KG neighbors: id that mediated the edge

    def to_dict(self) -> dict:
        d = {
            "path": self.path,
            "score": round(float(self.score), 4),
            "id": self.id,
            "name": self.name,
            "type": self.type,
        }
        if self.edge:
            d["edge"] = self.edge
        if self.via:
            d["via"] = self.via
        return d


@dataclass(slots=True)
class SearchResult:
    seeds: list[Hit] = field(default_factory=list)
    neighbors: list[Hit] = field(default_factory=list)
    drilldown: list[dict] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    low_confidence: bool = False  # top seed score < 0.55; drilldown recommended

    def to_dict(self) -> dict:
        return {
            "seeds": [h.to_dict() for h in self.seeds],
            "neighbors": [h.to_dict() for h in self.neighbors],
            "drilldown": self.drilldown,
            "trace": self.trace,
            "low_confidence": self.low_confidence,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# `[[concepts/concept-001.md|alias]]` or `[[entities/entity-002.md]]`
WIKILINK_RE = re.compile(r"\[\[([^\]\|]+\.md)(?:\|[^\]]*)?\]\]")
MD_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")


def _extract_links(md_text: str) -> list[str]:
    out: list[str] = []
    out.extend(WIKILINK_RE.findall(md_text))
    out.extend(MD_LINK_RE.findall(md_text))
    seen: set[str] = set()
    deduped: list[str] = []
    for raw in out:
        # strip leading ./ or wiki-output/ confusion later via index lookup
        link = raw.strip().lstrip("./")
        if link and link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def _normalize_to_wiki_path(link: str) -> str:
    """Wiki md files live under `wiki-output/`; on-disk links omit that prefix."""
    if link.startswith("wiki-output/"):
        return link
    return f"wiki-output/{link}"


# ---------------------------------------------------------------------------
# CaseIndex: cached loader for embeddings + registries.
# ---------------------------------------------------------------------------


class CaseIndex:
    def __init__(self, ws: Workspace):
        self.ws = ws

    @cached_property
    def embed_index(self) -> list[dict]:
        return json.loads(self.ws.read("cache/embeddings/index.json"))

    @cached_property
    def vectors(self) -> np.ndarray:
        # mmap to avoid loading 11 MB into RAM redundantly per process.
        path = self.ws._resolve("cache/embeddings/vectors.npy")  # type: ignore[attr-defined]
        v = np.load(path, mmap_mode="r")
        manifest_dim = self.manifest.get("dim")
        if manifest_dim is not None and v.shape[1] != manifest_dim:
            raise ValueError(
                f"vectors.npy shape {v.shape} does not match manifest dim {manifest_dim} "
                f"(model={self.manifest.get('model')!r})"
            )
        # pre-normalize for cosine via dot-product
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (v / norms).astype(np.float32, copy=False)

    @cached_property
    def manifest(self) -> dict:
        return json.loads(self.ws.read("cache/embeddings/manifest.json"))

    @cached_property
    def concept_registry(self) -> dict:
        return json.loads(self.ws.read("cache/concept_registry.json")).get("entries", {})

    @cached_property
    def entity_registry(self) -> dict:
        return json.loads(self.ws.read("cache/entity_registry.json")).get("entries", {})

    @cached_property
    def file_to_row(self) -> dict[str, int]:
        return {entry["file"]: i for i, entry in enumerate(self.embed_index)}

    @cached_property
    def id_to_file(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for reg in (self.concept_registry, self.entity_registry):
            for rid, meta in reg.items():
                f = meta.get("file")
                if f:
                    out[rid] = f
        return out

    @cached_property
    def source_id_to_files(self) -> dict[str, list[str]]:
        """Reverse index: source_id -> list of registry md files that reference it."""
        out: dict[str, list[str]] = {}
        for reg in (self.concept_registry, self.entity_registry):
            for meta in reg.values():
                f = meta.get("file")
                if not f:
                    continue
                for sid in meta.get("source_ids", []):
                    out.setdefault(str(sid), []).append(f)
        return out

    def hit_from_row(self, row: int, score: float, *, edge: str | None = None, via: str | None = None) -> Hit:
        entry = self.embed_index[row]
        return Hit(
            path=_normalize_to_wiki_path(entry["file"]),
            score=score,
            id=entry["id"],
            name=entry["name_ko"],
            type=entry["type"],
            edge=edge,
            via=via,
        )


# ---------------------------------------------------------------------------
# smart_search
# ---------------------------------------------------------------------------


def smart_search(
    ws: Workspace,
    embedder: Embedder,
    query: str,
    *,
    k: int = 10,
    hop: int = 1,
    max_neighbors: int = 10,
    drilldown: bool = False,
    _qvec: "np.ndarray | None" = None,
) -> SearchResult:
    """Lookup with priority wiki → cache → 1-hop KG → (optional) json/sources.

    Args:
        ws:         workspace bound to a case_id
        embedder:   query embedder (must produce same dim as the prebuilt index)
        query:      natural-language query
        k:          top-k seed hits from semantic search
        hop:        graph hops to expand (only 0 or 1 supported in MVP)
        max_neighbors: cap for neighbors after scoring
        drilldown:  if True, include json drill-down hints (json paths only,
                    not full text — caller decides what to read)
        _qvec:      pre-computed query vector (skips embedding if provided)
    """
    idx = CaseIndex(ws)
    res = SearchResult()

    # ---- 1. wiki-output: semantic search over registry md files ----
    qvec = (_qvec if _qvec is not None else embedder.embed(query)).astype(np.float32)
    if qvec.shape[0] != idx.vectors.shape[1]:
        raise ValueError(
            f"query embedding dim {qvec.shape[0]} != index dim {idx.vectors.shape[1]} "
            f"(index model={idx.manifest.get('model')!r}); "
            f"set CASE_AGENT_EMBED_DIM to match the index, or rebuild the index"
        )
    qnorm = np.linalg.norm(qvec)
    if qnorm == 0:
        res.trace.append("empty query embedding; aborting")
        return res
    qvec = qvec / qnorm

    sims: np.ndarray = idx.vectors @ qvec  # (N,)
    if sims.shape[0] < k:
        k = sims.shape[0]
    top_rows = np.argpartition(-sims, k - 1)[:k]
    top_rows = top_rows[np.argsort(-sims[top_rows])]
    seeds = [idx.hit_from_row(int(r), float(sims[int(r)]), edge="seed") for r in top_rows]
    res.seeds = seeds
    if seeds and seeds[0].score < 0.55:
        res.low_confidence = True
        res.trace.append(
            f"low-confidence: top score={seeds[0].score:.3f} < 0.55; drilldown recommended"
        )
    res.trace.append(f"wiki-embeddings: {len(seeds)} seed hits (model={idx.manifest.get('model')})")

    # ---- 2. cache: enrich seed registry metadata is implicit via ID; nothing to add here ----
    res.trace.append("cache: registries loaded; ids resolvable for drill-down")

    # ---- 3. 1-hop KG expansion ----
    if hop >= 1 and seeds:
        neighbors = _expand_one_hop(ws, idx, seeds, max_neighbors=max_neighbors)
        res.neighbors = neighbors
        res.trace.append(
            f"kg-expand: +{len(neighbors)} neighbors via link/registry "
            f"(max_neighbors={max_neighbors})"
        )

    # ---- 4. (optional) json/sources drill-down hints ----
    if drilldown:
        seen_source_ids: set[str] = set()
        for h in seeds + res.neighbors:
            # ID like "concept-002" / "entity-001" / "source-30"
            reg = idx.concept_registry.get(h.id) or idx.entity_registry.get(h.id)
            if reg:
                for sid in reg.get("source_ids", []):
                    seen_source_ids.add(str(sid))
        # Non-numeric ids (e.g. "공소장") first so key documents surface at the top.
        def _sid_sort_key(s: str) -> tuple:
            is_num = s.isdigit()
            return (int(is_num), int(s) if is_num else s)
        for sid in sorted(seen_source_ids, key=_sid_sort_key):
            if ws.exists(f"json/{sid}.json"):
                res.drilldown.append({"path": f"json/{sid}.json", "via_source_id": sid})
        res.trace.append(f"drilldown: {len(res.drilldown)} json source files referenced")

    return res


def _expand_one_hop(
    ws: Workspace,
    idx: CaseIndex,
    seeds: list[Hit],
    *,
    max_neighbors: int,
) -> list[Hit]:
    """Collect 1-hop neighbors via (a) explicit md links and (b) shared registry ids."""
    seed_paths: set[str] = {h.path for h in seeds}
    cand: dict[str, Hit] = {}  # path -> best Hit (dedup, keep highest score)

    def _bump(hit: Hit) -> None:
        prev = cand.get(hit.path)
        if prev is None or hit.score > prev.score:
            cand[hit.path] = hit

    # (a) explicit link edges: read each seed md, extract wikilinks/md links, look them up.
    for seed in seeds:
        try:
            text = ws.read(seed.path)
        except Exception:
            continue
        for raw in _extract_links(text):
            nbr = _normalize_to_wiki_path(raw)
            if nbr in seed_paths:
                continue
            row = idx.file_to_row.get(raw) or idx.file_to_row.get(nbr.removeprefix("wiki-output/"))
            if row is None:
                continue
            # score neighbor by seed's score (we don't re-embed neighbors here)
            _bump(idx.hit_from_row(row, seed.score * 0.8, edge="link", via=seed.id))

    # (b) registry-mediated edges: same source_id => connected.
    for seed in seeds:
        reg_meta = idx.concept_registry.get(seed.id) or idx.entity_registry.get(seed.id)
        if not reg_meta:
            continue
        for sid in reg_meta.get("source_ids", []):
            for other_file in idx.source_id_to_files.get(str(sid), ()):
                nbr_path = _normalize_to_wiki_path(other_file)
                if nbr_path in seed_paths:
                    continue
                row = idx.file_to_row.get(other_file)
                if row is None:
                    continue
                _bump(
                    idx.hit_from_row(
                        row, seed.score * 0.6, edge="concept" if seed.type == "concept" else "entity",
                        via=str(sid),
                    )
                )

    ranked = sorted(cand.values(), key=lambda h: h.score, reverse=True)
    return ranked[:max_neighbors]
