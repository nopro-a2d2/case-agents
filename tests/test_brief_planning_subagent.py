"""Structural checks for the kind-specific BriefPlanningAgent subagents.

We don't drive the LLM here — those are integration tests. Instead we verify:
- All kind-specific planner modules export ``build_subagent`` (currently
  ``brief_planning_civil`` and ``brief_planning_general``).
- Each planner's ``name`` matches ``BriefKind.planner_subagent_name``.
- Every planner shares the common READ-ONLY base prompt header.
- Every planner injects a kind-specific EXTRA (extras differ by kind).
- The tool list is the read-only set (smart_search, read_evidence,
  list_evidence) with no write_file.
- Discovery picks them up automatically.
"""

from __future__ import annotations

import importlib

import pytest

from case_agent.briefs import BRIEF_KINDS
from case_agent.subagents import discover_subagents
from case_agent.workspace import LocalFS

PLANNER_KEYS = sorted(BRIEF_KINDS)


class _StubEmbedder:
    """Embedder stub — planning subagents only need it to wire smart_search;
    we never invoke the tool here."""

    def embed_query(self, text: str) -> list[float]:  # pragma: no cover - unused
        return [0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover - unused
        return [[0.0] for _ in texts]


@pytest.fixture()
def ws() -> LocalFS:
    return LocalFS(case_id="spark", root="data")


@pytest.mark.parametrize("key", PLANNER_KEYS)
def test_planner_module_loadable(key: str) -> None:
    kind = BRIEF_KINDS[key]
    mod = importlib.import_module(f"case_agent.subagents.{kind.planner_subagent_name}")
    assert callable(getattr(mod, "build_subagent", None))


@pytest.mark.parametrize("key", PLANNER_KEYS)
def test_planner_builds_with_expected_name(ws: LocalFS, key: str) -> None:
    kind = BRIEF_KINDS[key]
    mod = importlib.import_module(f"case_agent.subagents.{kind.planner_subagent_name}")
    sa = mod.build_subagent(ws, _StubEmbedder())
    assert sa["name"] == kind.planner_subagent_name
    # READ-ONLY contract — the base prompt must declare it.
    assert "READ-ONLY MODE" in sa["system_prompt"]
    # JSON output schema must be documented in the prompt so the planner
    # returns parseable output to the main agent.
    assert "case_summary" in sa["system_prompt"]
    assert "strategy_direction" in sa["system_prompt"]
    assert "context_markdown" in sa["system_prompt"]
    assert "sections" in sa["system_prompt"]


def test_planner_extras_differ_across_kinds(ws: LocalFS) -> None:
    """Each kind must carry its own EXTRA — civil_brief vs general_brief."""
    prompts: dict[str, str] = {}
    for key in PLANNER_KEYS:
        kind = BRIEF_KINDS[key]
        mod = importlib.import_module(
            f"case_agent.subagents.{kind.planner_subagent_name}"
        )
        prompts[key] = mod.build_subagent(ws, _StubEmbedder())["system_prompt"]
    # Pairwise distinct.
    assert len({p for p in prompts.values()}) == len(prompts)
    # Spot-check kind-specific keywords appear only in their own prompt.
    assert "청구취지" in prompts["civil_brief"]
    # general_brief planner runs a 2-mode (asking/ready) interactive flow.
    assert '"asking"' in prompts["general_brief"]
    assert '"ready"' in prompts["general_brief"]


@pytest.mark.parametrize("key", PLANNER_KEYS)
def test_planner_has_readonly_tools_only(ws: LocalFS, key: str) -> None:
    """Planner must not have write_file. By default it gets read-only tools;
    the explore-only task tool is injected later in case_agent.agent."""
    kind = BRIEF_KINDS[key]
    mod = importlib.import_module(f"case_agent.subagents.{kind.planner_subagent_name}")
    sa = mod.build_subagent(ws, _StubEmbedder())
    tool_names = {t.name for t in sa["tools"]}
    assert "write_file" not in tool_names
    # Read-only baseline.
    assert "smart_search" in tool_names
    assert "read_evidence" in tool_names
    assert "list_evidence" in tool_names


def test_discover_subagents_picks_up_all_planners(ws: LocalFS) -> None:
    """Auto-discovery must register every brief_planning_<kind>."""
    subagents = discover_subagents(ws, _StubEmbedder())
    for key in PLANNER_KEYS:
        kind = BRIEF_KINDS[key]
        assert kind.planner_subagent_name in subagents, (
            f"discovery missed {kind.planner_subagent_name}"
        )
