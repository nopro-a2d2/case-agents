"""Top-level case-agent assembly.

Two entry points:

* :func:`build_case_agent_components` — returns the *parts* (model, tools,
  system prompt, subagents) so our hand-rolled loop in
  :mod:`case_agent.loop` can drive them directly. This is the path the CLI
  and TUI use. It mirrors claude-code's separation between query.ts (the
  loop) and the tools/agents it composes.

* :func:`build_case_agent` — returns a compiled DeepAgents/LangGraph agent.
  Kept for callers that still need the all-in-one object; new code should
  prefer the components builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend

from .model import VertexEmbedderAdapter, build_embedder, build_heavy, build_light
from .prompts import MAIN_SYSTEM_PROMPT
from .subagents import build_explore_subagent
from .tools.agent_tools import (
    build_check_completeness_tool,
    build_list_evidence_tool,
    build_read_with_anchor_tool,
    build_smart_search_tool,
    build_verify_citations_tool,
)
from .workspace import LocalFS

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from .tools.search import Embedder
    from .workspace import Workspace


@dataclass
class CaseAgentComponents:
    """Pre-assembled pieces our :mod:`case_agent.loop` consumes.

    ``subagents`` is a name-keyed dict of ``SubAgent`` definitions
    (deepagents shape: ``{name, system_prompt, tools, model?, ...}``).
    The loop's task tool looks them up by name when the main model emits
    a ``task(subagent_name=..., prompt=...)`` call.
    """

    workspace: "Workspace"
    model: "BaseChatModel"
    tools: list["BaseTool"]
    system_prompt: str
    subagents: dict[str, dict[str, Any]]


# Workspace-relative paths must start with `/` per FilesystemPermission's contract.
# Allow everything by default, then deny writes/edits to source directories.
_CASE_PERMISSIONS = [
    FilesystemPermission(operations=["read", "ls", "glob", "grep"], paths=["/**"], mode="allow"),
    FilesystemPermission(operations=["write", "edit"], paths=["/artifacts/**", "/drafts/**", "/notes/**", "/audit/**"], mode="allow"),
    FilesystemPermission(operations=["write", "edit"], paths=["/wiki-output/**", "/cache/**", "/json/**", "/sources/**", "/txt/**"], mode="deny"),
]


def build_case_agent_components(
    workspace: "Workspace",
    *,
    heavy_model: "BaseChatModel | None" = None,
    light_model: "BaseChatModel | None" = None,
    embedder: "Embedder | None" = None,
) -> CaseAgentComponents:
    """Assemble the parts our hand-rolled loop needs.

    Includes a ``task`` tool wired to the registered sub-agents, so the main
    model can delegate via ``task(subagent_name=..., prompt=...)`` exactly
    the way it would inside a DeepAgents graph.
    """
    if not isinstance(workspace, LocalFS):
        raise NotImplementedError(
            "Only LocalFS is wired today; S3FS support requires a custom "
            "BackendProtocol implementation."
        )

    main = heavy_model or build_heavy()
    sub_model = light_model or build_light()
    emb = embedder or build_embedder()

    case_tools: list[BaseTool] = [
        build_smart_search_tool(workspace, emb),
        build_read_with_anchor_tool(workspace),
        build_list_evidence_tool(workspace),
        build_verify_citations_tool(workspace),
        build_check_completeness_tool(workspace),
    ]

    explore = build_explore_subagent(workspace, emb, model=sub_model)
    subagents: dict[str, dict[str, Any]] = {explore["name"]: dict(explore)}

    # Wire the task tool last so the registry it captures is final.
    from .loop.task_tool import build_task_tool

    case_tools.append(build_task_tool(subagents=subagents, fallback_model=sub_model))

    return CaseAgentComponents(
        workspace=workspace,
        model=main,
        tools=case_tools,
        system_prompt=MAIN_SYSTEM_PROMPT,
        subagents=subagents,
    )


def build_case_agent(
    workspace: "Workspace",
    *,
    heavy_model: "BaseChatModel | None" = None,
    light_model: "BaseChatModel | None" = None,
    embedder: "Embedder | None" = None,
    checkpointer: "BaseCheckpointSaver | None" = None,
):
    """Compile a DeepAgent bound to a case workspace.

    Args:
        workspace: case_id-bound workspace (LocalFS today, S3FS later).
        heavy_model: override main model (defaults to Vertex Claude Sonnet).
        light_model: override sub-agent model (defaults to Vertex Gemini Flash).
        embedder: override smart_search embedder (defaults to Vertex gemini-embedding-2).
        checkpointer: optional LangGraph checkpointer to enable resumable
            sessions when invoked with ``config={"configurable": {"thread_id": ...}}``.
    """
    if not isinstance(workspace, LocalFS):
        raise NotImplementedError(
            "Only LocalFS is wired through DeepAgents' FilesystemBackend today; "
            "S3FS support requires a custom BackendProtocol implementation."
        )

    main = heavy_model or build_heavy()
    sub_model = light_model or build_light()
    emb = embedder or build_embedder()

    # virtual_mode=True keeps absolute paths and '..' from escaping the case root.
    backend = FilesystemBackend(root_dir=str(workspace.case_root), virtual_mode=True)

    explore = build_explore_subagent(workspace, emb, model=sub_model)

    kwargs = {
        "model": main,
        "tools": [
            build_smart_search_tool(workspace, emb),
            build_read_with_anchor_tool(workspace),
            build_list_evidence_tool(workspace),
            build_verify_citations_tool(workspace),
            build_check_completeness_tool(workspace),
        ],
        "system_prompt": MAIN_SYSTEM_PROMPT,
        "subagents": [explore],
        "backend": backend,
        "permissions": _CASE_PERMISSIONS,
    }
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    return create_deep_agent(**kwargs)


__all__ = [
    "CaseAgentComponents",
    "VertexEmbedderAdapter",
    "build_case_agent",
    "build_case_agent_components",
]
