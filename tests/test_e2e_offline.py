"""Offline end-to-end golden scenario.

Runs the agentic loop against the bundled `spark` case using:
  - a deterministic dummy embedder (RowEmbedder pinned to one md row),
  - a known-valid citation to verify the full Gather → Act → Verify cycle.

Note: the live Vertex models are not exercised here — that's a separate
integration test that needs GCP_PROJECT.
"""

from __future__ import annotations

import numpy as np
import pytest

from case_agent.tools.search import CaseIndex, smart_search
from case_agent.tools.verify import verify_citations
from case_agent.workspace import LocalFS


CASE_ID = "spark"


class _RowEmbedder:
    def __init__(self, idx: CaseIndex, target_file: str):
        row = idx.file_to_row[target_file]
        self._vec = np.array(idx.vectors[row], dtype=np.float32)

    def embed(self, text: str) -> np.ndarray:  # noqa: ARG002
        return self._vec


@pytest.fixture()
def ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


def test_offline_qna_pipeline_end_to_end(ws: LocalFS) -> None:
    """Walk the Gather → Act → Verify cycle without going to Vertex.

    The 'Q&A' scenario from the plan: ask about the gobaljang's claims, gather
    via smart_search, write an artifact citing source-1 page 1, and verify.
    """
    idx = CaseIndex(ws)
    emb = _RowEmbedder(idx, "concepts/concept-018.md")  # 업무상 배임 → source-1 in registry

    # ---- ① Gather: smart_search returns seeds + KG neighbors + drilldown ----
    res = smart_search(ws, emb, "업무상 배임 의혹", k=5, hop=1, drilldown=True)
    assert res.seeds[0].path == "wiki-output/concepts/concept-018.md"
    # KG expansion should produce neighbors via shared source_ids / md links.
    assert res.neighbors, "concept-018 should have KG neighbors"
    # `drilldown=True` should surface json/1.json (the underlying source).
    drilldown_paths = {d["path"] for d in res.drilldown}
    assert "json/1.json" in drilldown_paths
    # search_trace records each phase
    assert any("wiki-embeddings" in t for t in res.trace)
    assert any("kg-expand" in t for t in res.trace)

    # ---- ② Act: write an artifact citing what we just retrieved ----
    artifact_path = "artifacts/_e2e_qna.md"
    ws.write(
        artifact_path,
        "# 고발장 핵심 주장 요약 (offline e2e)\n\n"
        "1. 일감몰아주기 의혹: KDFS의 KT텔레캅 물량이 16년 45억 → 22년 490억대로 증가했다는 주장 (@@[1]).\n"
        "2. 고발취지: 시민단체 '정의로운 사람들'이 형법상 배임 등의 혐의로 고발 (@@[1]).\n"
        "3. 결론: 정당하고 신속하고 철저한 수사를 요청 (@@[1]).\n",
    )

    # ---- ③ Verify: every @@[id] must resolve against the id registry ----
    rep = verify_citations(ws, artifact_path)
    assert rep.total == 1  # all three @@[1] occurrences dedupe to one
    assert rep.failed == 0
    assert rep.ok is True

    # Audit trail recorded the artifact write.
    audit_log = (ws.case_root / "audit" / "ops.jsonl").read_text(encoding="utf-8")
    assert artifact_path in audit_log


