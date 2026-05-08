"""LangChain Tool wrappers exposing case-aware primitives to a DeepAgent.

These complement DeepAgents' built-in filesystem tools (which run against the
agent's `FilesystemBackend` rooted at the case directory). Our tools enforce
the lookup priority (wiki → cache → 1-hop KG → json → sources) and the
single-form citation grammar `path#anchor`.

All tools are case-bound via closure capture of `(workspace, embedder)`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import tool

from ..workspace import Workspace
from .calculate import CalculateTool
from .citation import list_evidence as _list_evidence, read_with_anchor as _read_with_anchor
from .search import Embedder, smart_search as _smart_search
from .verify import (
    check_completeness as _check_completeness,
    verify_citations as _verify_citations,
)


def build_smart_search_tool(workspace: Workspace, embedder: Embedder):
    @tool
    async def smart_search(
        query: str,
        k: int = 8,
        hop: int = 1,
        max_neighbors: int = 10,
        drilldown: bool = True,
    ) -> str:
        """Find case knowledge by semantic search over wiki-output, with optional 1-hop KG expansion.

        Order is enforced: wiki-output embeddings → cache registries → 1-hop neighbors
        (explicit md links + shared concept/entity ids) → optional json/source drill-down.
        Use this BEFORE reading raw json/ or sources/ files. Returns JSON with
        seeds (top-k semantic hits), neighbors (1-hop KG, with `edge` and `via` annotations),
        drilldown (json paths only — read them if you still need page-anchored evidence),
        and trace (per-phase hit/miss notes).

        Args:
            query: natural-language Korean or English query (e.g. "임의제출 절차 위법성").
            k: top-k seed hits (default 8).
            hop: graph hops; 0 disables KG expansion, 1 (default) enables one hop.
            max_neighbors: cap for KG neighbors after scoring (default 10).
            drilldown: if True, list json/<source>.json paths referenced by hits.
        """
        async with asyncio.timeout(30):
            qvec = await embedder.aembed(query)
        result = _smart_search(
            workspace,
            embedder,
            query,
            k=k,
            hop=hop,
            max_neighbors=max_neighbors,
            drilldown=drilldown,
            _qvec=qvec,
        )
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

    return smart_search


def build_read_with_anchor_tool(workspace: Workspace):
    @tool
    def read_with_anchor(citation: str, max_chars: int = 4000) -> str:
        """Read a workspace file region keyed by an anchor.

        Citation grammar: `path#anchor` where anchor is one of:
          - `Lstart-Lend`   line range, 1-based (txt files)
          - `pN`            single page              (json source files)
          - `pA..B`         inclusive page range    (json source files)
                            e.g. `json/1.json#p1..5` reads pages 1–5 in one call.
                            한 번에 여러 페이지를 가져와 토큰을 절약하세요.
                            범위 구분자는 반드시 `..` 입니다 (`p1-5` ❌, `p1..5` ✅).
                            반환 스니펫에는 페이지 경계마다 `--- pN ---` 마커가 들어갑니다.
          - `sec:slug`      heading slug     (markdown wiki files)

        Returns JSON with the (canonical) `citation`, the `snippet` text, and `kind`.
        Use this to FETCH the exact wording you will paste into artifacts/drafts so
        verify_citations later accepts the citation.
        """
        out = _read_with_anchor(workspace, citation, max_chars=max_chars)
        return json.dumps(out.to_dict(), ensure_ascii=False)

    return read_with_anchor


def build_list_evidence_tool(workspace: Workspace):
    @tool
    def list_evidence(
        person: str | None = None,
        category: str | None = None,
        name_contains: str | None = None,
        limit: int = 50,
    ) -> str:
        """Enumerate evidence (json/) with optional filters.

        Each item gives the source_id, title, category, person, page count, the
        json_path you can `read_with_anchor` against (with `pN` or `pA..B` anchors), and the
        wiki_path of its summary md if available. Useful when the user references
        an evidence number or wants a specific class of documents.
        """
        items = _list_evidence(
            workspace,
            person=person,
            category=category,
            name_contains=name_contains,
            limit=limit,
        )
        return json.dumps([it.to_dict() for it in items], ensure_ascii=False, indent=2)

    return list_evidence


def build_verify_citations_tool(workspace: Workspace):
    @tool
    def verify_citations(path: str) -> str:
        """Verify every `path#anchor` citation embedded in an artifact/draft.

        Reads the file at `path`, finds every citation token, attempts to
        resolve each via `read_with_anchor`, and returns a JSON report with
        per-citation pass/fail. If `failed > 0`, you MUST fix the failing
        citations before claiming completion.
        """
        return json.dumps(_verify_citations(workspace, path).to_dict(), ensure_ascii=False, indent=2)

    return verify_citations


def build_check_completeness_tool(workspace: Workspace):
    @tool
    def check_completeness(kind: str, path: str) -> str:
        """Run a doctype-specific structural checklist on an artifact/draft.

        kind options:
          - 'evidence_acknowledgment'  (증거인부서)
          - 'witness_questions'        (증인심문사항)
          - 'defendant_questions'      (피고인심문사항)
          - 'defense_opinion'          (변호인 의견서)
          - 'civil_brief'              (민사 준비서면)
          - 'evidence_pros_cons'       (증거 유불리표 artifact)
          - 'timeline'                 (연표 artifact)
          - 'issues'                   (쟁점표 artifact)

        Returns JSON listing missing sections / rule violations. ok=true means
        the doc passes the checklist.
        """
        return json.dumps(
            _check_completeness(workspace, kind, path).to_dict(),
            ensure_ascii=False,
            indent=2,
        )

    return check_completeness


def build_calculate_tool() -> CalculateTool:
    """Return a CalculateTool instance (no workspace dependency)."""
    return CalculateTool()


def build_write_file_tool(workspace: Workspace):
    @tool
    def write_file(path: str, content: str) -> str:
        """Write ``content`` to a workspace-relative ``path`` (overwrite if exists).

        쓰기 가능 디렉토리: ``artifacts/``, ``audit/``, ``plans/``, ``memory/``,
        ``state/``, (legacy) ``drafts/``, ``notes/``. ``MEMORY.md`` 는 루트 허용.
        ``wiki-output/``, ``cache/``, ``json/``, ``sources/``, ``txt/`` 는 read-only —
        쓰기 시 에러를 반환합니다.

        Args:
            path: workspace-root-relative path, e.g. ``artifacts/timeline_v1.md``.
            content: full file contents (UTF-8 text). Existing file is overwritten.

        Returns:
            ``"wrote {path}"`` on success.
        """
        workspace.write(path, content)
        return f"wrote {path}"

    return write_file


def build_case_tools(workspace: Workspace, embedder: Embedder) -> list[Any]:
    """Convenience: every case-aware tool."""
    return [
        build_smart_search_tool(workspace, embedder),
        build_read_with_anchor_tool(workspace),
        build_list_evidence_tool(workspace),
        build_verify_citations_tool(workspace),
        build_check_completeness_tool(workspace),
        build_calculate_tool(),
        build_write_file_tool(workspace),
    ]
