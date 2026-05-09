"""Subagent registry with auto-discovery.

Drop a new file ``case_agent/subagents/<name>.py`` that exports a
``build_subagent(workspace, embedder, *, model=None) -> dict`` factory; it
gets picked up automatically by :func:`discover_subagents`. Modules whose
names start with ``_`` are skipped.

Backward-compat: ``build_explore_subagent`` is still re-exported.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Any

from .explore import build_explore_subagent

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.search import Embedder
    from ..workspace import Workspace


def discover_subagents(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, dict[str, Any]]:
    """Auto-import every non-underscore sibling module and call its
    ``build_subagent`` factory; aggregate by ``sa["name"]``.
    """
    out: dict[str, dict[str, Any]] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f".{info.name}", __package__)
        builder = getattr(mod, "build_subagent", None)
        if builder is None:
            continue
        sa = builder(workspace, embedder, model=model)
        out[sa["name"]] = dict(sa)
    return out


__all__ = ["build_explore_subagent", "discover_subagents"]
