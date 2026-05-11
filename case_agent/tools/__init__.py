"""Tool registry — single entry point so ``agent.py`` doesn't need to know
which builder lives in which module.

Add a new tool by either:

* dropping a builder into one of the existing domain modules (search.py,
  citation.py, verify.py, …) and adding it to :func:`build_all_tools` here;
* or creating a new ``case_agent/tools/<topic>.py`` with a ``build_*_tool``
  factory and importing it here.

Keep this file thin — assembly only, no behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .agent_tools import build_case_tools
from .brief import build_brief_mode_tools
from .memory import build_memory_tools
from .skill import build_skill_tool
from .strategy import build_strategy_tools
from .todos import TodoStore, build_write_todos_tool

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from ..skills import Skill
    from ..workspace import Workspace
    from .search import Embedder


def build_all_tools(
    workspace: "Workspace",
    embedder: "Embedder",
    todos_store: TodoStore,
    skills_registry: "dict[str, Skill] | None" = None,
) -> list["BaseTool"]:
    """Return every tool the main agent should see, in display order.

    When ``skills_registry`` is non-empty, the ``skill`` tool is appended
    so the model can load SKILL.md bodies on demand.
    """
    tools: list[BaseTool] = []
    tools.extend(build_case_tools(workspace, embedder))
    tools.extend(build_memory_tools(workspace))
    tools.extend(build_strategy_tools(workspace))
    tools.extend(build_brief_mode_tools(workspace, todos_store))
    tools.append(build_write_todos_tool(todos_store))
    if skills_registry:
        tools.append(build_skill_tool(skills_registry))
    return tools


__all__ = ["TodoStore", "build_all_tools"]
