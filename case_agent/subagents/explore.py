"""Explore sub-agent: case-document scout running on Gemini Flash.

Single low-level capability: rip through wiki/cache/json/sources via smart_search
and read_with_anchor, return citation-rich JSON. No write/edit. No analysis.
Lives in an isolated context so the main (Sonnet) agent's window stays clean.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..prompts import EXPLORE_SYSTEM_PROMPT
from ..tools.agent_tools import (
    build_read_with_anchor_tool,
    build_smart_search_tool,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.search import Embedder
    from ..workspace import Workspace


def build_explore_subagent(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, Any]:
    tools: list[Any] = [
        build_smart_search_tool(workspace, embedder),
        build_read_with_anchor_tool(workspace),
    ]
    sa: dict[str, Any] = {
        "name": "explore",
        "description": (
            "Search and read case documents (wiki/cache/json/sources) and return "
            "a citation-rich JSON summary. Use this when you need to gather "
            "evidence excerpts without polluting your own context. The sub-agent "
            "cannot write or edit files."
        ),
        "system_prompt": EXPLORE_SYSTEM_PROMPT,
        "tools": tools,
    }
    if model is not None:
        sa["model"] = model
    return sa


build_subagent = build_explore_subagent

