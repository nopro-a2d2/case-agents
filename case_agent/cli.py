"""CLI for case-agent.

Examples:
    case-agent run --case spark "공소장의 핵심 공소사실 3가지를 증거번호와 함께 요약해줘"
    case-agent search --case spark "임의제출 절차 위법성"
    case-agent verify --case spark drafts/증거인부서_v1.md
    case-agent ls    --case spark wiki-output/concepts | head
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel

from case_agent.tools.citation import list_evidence as _list_evidence
from case_agent.tools.citation import read_evidence as _read_evidence
from case_agent.tools.search import smart_search
from case_agent.tools.verify import check_completeness, verify_citations
from case_agent.workspace import LocalFS

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Case-Agent CLI")
console = Console()


def _ws(case_id: str, root: str) -> LocalFS:
    return LocalFS(case_id=case_id, root=root)


@app.command()
def run(
    prompt: Annotated[str, typer.Argument(help="Question or instruction.")],
    case: Annotated[str, typer.Option("--case", "-c", help="Case id (data/{case}/...)")] = "spark",
    root: Annotated[str, typer.Option("--root", help="Workspace root.")] = "data",
    session_id: Annotated[
        str | None,
        typer.Option(
            "--session-id",
            help="Optional Langfuse session_id to group this run with others.",
        ),
    ] = None,
) -> None:
    """Run a one-shot query against the DeepAgent."""
    import asyncio

    from case_agent.agent import build_case_agent_components
    from case_agent.loop import run_query_oneshot

    ws = _ws(case, root)
    console.print(Panel(f"case={ws.case_id}  root={ws.case_root}", title="case-agent"))
    components = build_case_agent_components(ws)
    text = asyncio.run(
        run_query_oneshot(prompt, components, session_id=session_id)
    )
    console.print(Panel(text or "(empty reply)", title="reply"))


@app.command()
def search(
    query: Annotated[str, typer.Argument()],
    case: Annotated[str, typer.Option("--case", "-c")] = "spark",
    root: Annotated[str, typer.Option("--root")] = "data",
    k: Annotated[int, typer.Option("-k")] = 5,
    hop: Annotated[int, typer.Option("--hop")] = 1,
    drilldown: Annotated[bool, typer.Option("--drilldown/--no-drilldown")] = True,
) -> None:
    """Run smart_search alone (requires GCP for the embedder)."""
    from case_agent.model import build_embedder

    ws = _ws(case, root)
    res = smart_search(
        ws, build_embedder(), query, k=k, hop=hop, drilldown=drilldown
    )
    console.print(JSON(json.dumps(res.to_dict(), ensure_ascii=False)))


@app.command()
def evidence(
    case: Annotated[str, typer.Option("--case", "-c")] = "spark",
    root: Annotated[str, typer.Option("--root")] = "data",
    name: Annotated[str | None, typer.Option("--name")] = None,
    person: Annotated[str | None, typer.Option("--person")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
) -> None:
    """List evidence (json/) with optional filters. No GCP needed."""
    ws = _ws(case, root)
    items = _list_evidence(ws, name_contains=name, person=person, limit=limit)
    console.print(
        JSON(json.dumps([it.to_dict() for it in items], ensure_ascii=False))
    )


@app.command()
def cite(
    id: Annotated[str, typer.Argument(help="value of the evidence json `id` field (e.g. 1, cdoc_01KK...)")],
    start_page: Annotated[int | None, typer.Option("--start-page", "-p")] = None,
    end_page: Annotated[int | None, typer.Option("--end-page")] = None,
    section_id: Annotated[str | None, typer.Option("--section-id")] = None,
    case: Annotated[str, typer.Option("--case", "-c")] = "spark",
    root: Annotated[str, typer.Option("--root")] = "data",
    chars: Annotated[int, typer.Option("--chars")] = 1500,
) -> None:
    """Read a region of an evidence document by id. No GCP needed."""
    ws = _ws(case, root)
    out = _read_evidence(
        ws,
        id,
        start_page=start_page,
        end_page=end_page,
        section_id=section_id,
        max_chars=chars,
    )
    console.print(Panel(out.snippet, title=f"{out.citation}  ({out.kind})"))


@app.command()
def verify(
    path: Annotated[str, typer.Argument(help="artifact/draft path within the case")],
    case: Annotated[str, typer.Option("--case", "-c")] = "spark",
    root: Annotated[str, typer.Option("--root")] = "data",
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="If given, also run check_completeness."),
    ] = None,
) -> None:
    """Verify citations (and optionally completeness) of an artifact/draft."""
    ws = _ws(case, root)
    cite_rep = verify_citations(ws, path)
    console.print(
        JSON(json.dumps({"verify_citations": cite_rep.to_dict()}, ensure_ascii=False))
    )
    if kind:
        comp = check_completeness(ws, kind, path)
        console.print(
            JSON(json.dumps({"check_completeness": comp.to_dict()}, ensure_ascii=False))
        )


@app.command()
def ls(
    path: Annotated[str, typer.Argument()] = ".",
    case: Annotated[str, typer.Option("--case", "-c")] = "spark",
    root: Annotated[str, typer.Option("--root")] = "data",
) -> None:
    """List workspace contents at `path`."""
    ws = _ws(case, root)
    for entry in ws.ls(path):
        console.print(entry)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
