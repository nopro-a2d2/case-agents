"""Top-level case-agent assembly.

:func:`build_case_agent_components` returns the parts (model, tools,
system prompt, subagents) so the hand-rolled loop in :mod:`case_agent.loop`
can drive them directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .commands import Command, CommandHandler, discover_commands
from .model import VertexEmbedderAdapter, build_embedder, build_heavy, build_light
from .prompts import MAIN_SYSTEM_PROMPT
from .skills import Skill, discover_skills
from .loop.task_tool import build_task_tool, build_task_tool_for_subagent
from .skills.prompt import build_skill_listing
from .subagents import discover_subagents
from .tools import TodoStore, build_all_tools
from .workspace import LocalFS

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

    from .guardrails import GuardrailManager
    from .tools.search import Embedder
    from .workspace import Workspace


_BUNDLED_SKILLS_DIR = Path(__file__).parent / "skills" / "bundled"


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
    skills: dict[str, Skill] = field(default_factory=dict)
    commands: dict[str, tuple[Command, CommandHandler]] = field(default_factory=dict)
    guardrails: "GuardrailManager | None" = None


def build_case_agent_components(
    workspace: "Workspace",
    *,
    heavy_model: "BaseChatModel | None" = None,
    light_model: "BaseChatModel | None" = None,
    embedder: "Embedder | None" = None,
    enable_guardrails: bool = True,
    guardrails: "GuardrailManager | None" = None,
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

    todos_store = TodoStore()

    skills = discover_skills(
        _BUNDLED_SKILLS_DIR,
        workspace.case_root / "skills",  # workspace wins on collision
    )

    case_tools: list[BaseTool] = build_all_tools(workspace, emb, todos_store, skills)

    subagents: dict[str, dict[str, Any]] = discover_subagents(
        workspace, emb, model=sub_model
    )

    # brief subagents get an explore-only `task` tool to prevent recursive brief delegation.
    if "explore" in subagents:
        restricted_task = build_task_tool_for_subagent(
            subagents=subagents,
            allowed={"explore"},
            fallback_model=sub_model,
        )
        for name, sa in subagents.items():
            if name.startswith("brief_"):
                sa["tools"] = list(sa.get("tools") or []) + [restricted_task]

    case_tools.append(build_task_tool(subagents=subagents, fallback_model=sub_model))

    system_prompt = MAIN_SYSTEM_PROMPT
    listing = build_skill_listing(skills)
    if listing:
        system_prompt = f"{MAIN_SYSTEM_PROMPT}\n\n{listing}"

    commands = discover_commands()

    effective_guardrails = guardrails
    if effective_guardrails is None and enable_guardrails:
        from .guardrails import build_default_guardrails

        effective_guardrails = build_default_guardrails()

    return CaseAgentComponents(
        workspace=workspace,
        model=main,
        tools=case_tools,
        system_prompt=system_prompt,
        subagents=subagents,
        todos_store=todos_store,
        skills=skills,
        commands=commands,
        guardrails=effective_guardrails,
    )



__all__ = [
    "CaseAgentComponents",
    "VertexEmbedderAdapter",
    "build_case_agent_components",
]
