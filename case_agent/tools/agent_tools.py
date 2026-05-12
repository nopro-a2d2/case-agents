"""LangChain Tool wrappers exposing case-aware primitives to a DeepAgent.

These complement DeepAgents' built-in filesystem tools (which run against the
agent's `FilesystemBackend` rooted at the case directory). Our tools enforce
the lookup priority (wiki → cache → 1-hop KG → json → sources) and the
single-form citation grammar `@@[id]`.

All tools are case-bound via closure capture of `(workspace, embedder)`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import tool

from case_agent.tools.calculate import CalculateTool
from case_agent.tools.citation import list_evidence as _list_evidence
from case_agent.tools.citation import read_evidence as _read_evidence
from case_agent.tools.search import Embedder
from case_agent.tools.search import smart_search as _smart_search
from case_agent.tools.verify import check_completeness as _check_completeness
from case_agent.tools.verify import verify_citations as _verify_citations
from case_agent.workspace import Workspace


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


def build_read_evidence_tool(workspace: Workspace):
    @tool
    def read_evidence(
        id: str,
        start_page: int | None = None,
        end_page: int | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        section_id: str | None = None,
        max_chars: int = 4000,
    ) -> str:
        """Read a region of an evidence document keyed by ``id``.

        Citation grammar: `@@[id]` (single id token, no anchor). ``id`` is
        the value of the top-level ``"id"`` field in the source json file.
        Get candidate ids from ``list_evidence`` or ``smart_search``.

        Addressing parameters (use at most one mode per call):
          - ``start_page`` (+ optional ``end_page``) — page range in json source.
            한 번에 여러 페이지를 가져와 토큰을 절약하세요.
            반환 스니펫에는 페이지 경계마다 ``--- pN ---`` 마커가 들어갑니다.
          - ``start_line`` (+ optional ``end_line``) — line range in text files.
          - ``section_id`` — heading slug (markdown wiki files).
          - none — return the document's full ``content`` body.

        Returns JSON: ``citation`` (canonical ``@@[id]``), ``id``,
        ``json_path``, ``snippet`` text, ``kind`` ("page"|"lines"|"section"|"full").
        Use this to FETCH the exact wording you will paste into
        artifacts/briefs so ``verify_citations`` later accepts the ``@@[id]``
        citation. The citation token itself never contains an anchor — page or
        line context belongs in surrounding prose, not in the citation.
        """
        out = _read_evidence(
            workspace,
            id,
            start_page=start_page,
            end_page=end_page,
            start_line=start_line,
            end_line=end_line,
            section_id=section_id,
            max_chars=max_chars,
        )
        return json.dumps(out.to_dict(), ensure_ascii=False)

    return read_evidence


def build_list_evidence_tool(workspace: Workspace):
    @tool
    def list_evidence(
        person: str | None = None,
        category: str | None = None,
        name_contains: str | None = None,
        limit: int = 50,
    ) -> str:
        """Enumerate evidence (json/) with optional filters.

        Each item gives the ``id`` (use this in ``@@[id]`` citations and as
        the ``id`` argument to ``read_evidence``), title, number (e.g.
        "갑 제3호증"), category, person, page count, json_path, and the
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
        """Verify every `@@[id]` citation embedded in an artifact/draft.

        Reads the file at `path`, finds every `@@[id]` token, checks that
        each id exists in the workspace evidence registry, and returns a JSON
        report with per-citation pass/fail. If `failed > 0`, you MUST fix the
        failing citations before claiming completion.
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
          - 'civil_brief'              (민사 준비서면, briefs/)
          - 'general_brief'            (범용 서면, briefs/)
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

        쓰기 가능 디렉토리: ``artifacts/`` (분석 산출물), ``briefs/`` (서면 —
        민사 준비서면 / 그 외 범용 서면), ``audit/``, ``plans/``, ``memory/``,
        ``state/``, (legacy) ``drafts/``, ``notes/``. ``MEMORY.md`` 는 루트 허용.
        ``wiki-output/``, ``cache/``, ``json/``, ``sources/``, ``txt/`` 는 read-only —
        쓰기 시 에러를 반환합니다.

        Args:
            path: workspace-root-relative path, e.g. ``artifacts/timeline_v1.md``
                or ``briefs/civil_brief_v1.md``.
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
        build_read_evidence_tool(workspace),
        build_list_evidence_tool(workspace),
        build_verify_citations_tool(workspace),
        build_check_completeness_tool(workspace),
        build_calculate_tool(),
        build_write_file_tool(workspace),
    ]
