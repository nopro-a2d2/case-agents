"""Tests for smart_search — uses an offline 'dummy' embedder so no GCP needed.

The dummy embedder picks a target row by query keyword and returns that row's
own (already-normalized) vector. That guarantees the picked row is the top hit,
which lets us cleanly test priority order, 1-hop KG expansion edges, and dedup.
"""

from __future__ import annotations

import numpy as np

from case_agent.tools.search import (
    CaseIndex,
    SearchResult,
    _extract_links,
    smart_search,
)
from case_agent.workspace import LocalFS


CASE_ID = "spark"


class _RowEmbedder:
    """Returns the prebuilt row vector for a target file path so it tops the search."""

    def __init__(self, idx: CaseIndex, target_file: str):
        row = idx.file_to_row[target_file]
        # vectors are already L2-normalized inside CaseIndex.
        self._vec = np.array(idx.vectors[row], dtype=np.float32)

    def embed(self, text: str) -> np.ndarray:  # noqa: ARG002
        return self._vec


def _ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


def test_extract_links_handles_both_styles() -> None:
    md = (
        "see [[concepts/concept-001.md|시장]] and "
        "[a normal](entities/entity-002.md) plus [[entities/entity-003.md]]"
    )
    links = _extract_links(md)
    assert "concepts/concept-001.md" in links
    assert "entities/entity-002.md" in links
    assert "entities/entity-003.md" in links


def test_smart_search_seed_is_top_hit() -> None:
    ws = _ws()
    idx = CaseIndex(ws)
    target = "concepts/concept-002.md"  # 임의제출
    emb = _RowEmbedder(idx, target)

    res: SearchResult = smart_search(ws, emb, "임의제출", k=5, hop=1)
    assert res.seeds, "should produce at least one seed"
    assert res.seeds[0].path == f"wiki-output/{target}"
    assert res.seeds[0].edge == "seed"
    # registry concepts have type "concept" in index
    assert res.seeds[0].type == "concept"


def test_smart_search_one_hop_neighbors_present() -> None:
    ws = _ws()
    idx = CaseIndex(ws)
    target = "concepts/concept-002.md"  # 임의제출 - rich wikilink graph
    emb = _RowEmbedder(idx, target)

    res = smart_search(ws, emb, "임의제출", k=3, hop=1, max_neighbors=10)
    assert res.neighbors, "concept-002 should expose explicit wikilink neighbors"

    # every neighbor must carry edge + via, and live under wiki-output/
    for n in res.neighbors:
        assert n.edge in {"link", "concept", "entity"}
        assert n.via, f"neighbor missing 'via': {n}"
        assert n.path.startswith("wiki-output/")

    # neighbor paths must be unique and must not collide with seeds
    seed_paths = {h.path for h in res.seeds}
    nbr_paths = [n.path for n in res.neighbors]
    assert len(nbr_paths) == len(set(nbr_paths))  # dedup
    assert seed_paths.isdisjoint(set(nbr_paths))  # no overlap


def test_smart_search_max_neighbors_respected() -> None:
    ws = _ws()
    idx = CaseIndex(ws)
    emb = _RowEmbedder(idx, "entities/entity-001.md")  # 윤경림: very high-degree node
    res = smart_search(ws, emb, "윤경림", k=3, hop=1, max_neighbors=5)
    assert len(res.neighbors) <= 5


def test_smart_search_drilldown_links_to_json_sources() -> None:
    ws = _ws()
    idx = CaseIndex(ws)
    emb = _RowEmbedder(idx, "concepts/concept-002.md")
    res = smart_search(ws, emb, "임의제출", k=3, hop=1, drilldown=True)
    assert res.drilldown, "drilldown should surface at least one json source"
    for d in res.drilldown:
        assert d["path"].startswith("json/") and d["path"].endswith(".json")
        assert ws.exists(d["path"])


def test_trace_records_each_phase() -> None:
    ws = _ws()
    idx = CaseIndex(ws)
    emb = _RowEmbedder(idx, "concepts/concept-002.md")
    res = smart_search(ws, emb, "임의제출", k=3, hop=1, drilldown=True)
    joined = " | ".join(res.trace)
    assert "wiki-embeddings" in joined
    assert "kg-expand" in joined
    assert "drilldown" in joined
