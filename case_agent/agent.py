"""Top-level case-agent assembly.

:func:`build_case_agent_components` returns the parts (model, tools,
system prompt, subagents) so the hand-rolled loop in :mod:`case_agent.loop`
can drive them directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .model import VertexEmbedderAdapter, build_embedder, build_heavy, build_light
from .prompts import MAIN_SYSTEM_PROMPT
from .subagents import build_explore_subagent
from .tools.agent_tools import (
    build_calculate_tool,
    build_check_completeness_tool,
    build_list_evidence_tool,
    build_read_with_anchor_tool,
    build_smart_search_tool,
    build_verify_citations_tool,
)
from .tools.memory import build_memory_tools
from .tools.strategy import build_strategy_tools
from .tools.todos import TodoStore, build_write_todos_tool
from .workspace import LocalFS

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

    from .tools.search import Embedder
    from .workspace import Workspace


@dataclass
class CaseAgentComponents:
    """Pre-assembled pieces our :mod:`case_agent.loop` consumes.

    ``subagents`` is a name-keyed dict of subagent definitions
    ``{name, system_prompt, tools, model?, ...}``.
    The loop's task tool looks them up by name when the main model emits
    a ``task(subagent_name=..., prompt=...)`` call.
    """

    workspace: "Workspace"
    model: "BaseChatModel"
    tools: list["BaseTool"]
    system_prompt: str
    subagents: dict[str, dict[str, Any]]
    todos_store: TodoStore


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
        build_calculate_tool(),
    ]
    case_tools.extend(build_memory_tools(workspace))
    case_tools.extend(build_strategy_tools(workspace))

    todos_store = TodoStore()
    case_tools.append(build_write_todos_tool(todos_store))

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
        todos_store=todos_store,
    )



__all__ = [
    "CaseAgentComponents",
    "VertexEmbedderAdapter",
    "build_case_agent_components",
]
