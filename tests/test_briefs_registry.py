"""Briefs registry — sanity checks that every BriefKind wires through.

Each entry in BRIEF_KINDS must (a) have a matching subagent module exporting
build_subagent, (b) have its doc_kind present in verify._REQUIRED_HEADINGS,
and (c) the briefs output path must land under the writable briefs/ prefix.
"""

from __future__ import annotations

import importlib

import pytest

from case_agent.briefs import BRIEF_KINDS, briefs_output_path, find_kind
from case_agent.tools.verify import _REQUIRED_HEADINGS
from case_agent.workspace.base import WRITABLE_PREFIXES


@pytest.mark.parametrize("key", sorted(BRIEF_KINDS))
def test_subagent_module_loadable(key: str) -> None:
    kind = BRIEF_KINDS[key]
    mod = importlib.import_module(f"case_agent.subagents.{kind.subagent_name}")
    assert callable(getattr(mod, "build_subagent", None)), (
        f"subagent module {kind.subagent_name} missing build_subagent"
    )


@pytest.mark.parametrize("key", sorted(BRIEF_KINDS))
def test_planner_subagent_name_set_and_loadable(key: str) -> None:
    """Every kind must declare a planner subagent_name AND its module must
    exist with a build_subagent factory — mirror of the writer check."""
    kind = BRIEF_KINDS[key]
    assert kind.planner_subagent_name, (
        f"BRIEF_KINDS[{key!r}].planner_subagent_name is unset"
    )
    assert kind.planner_subagent_name.startswith("brief_planning_")
    mod = importlib.import_module(
        f"case_agent.subagents.{kind.planner_subagent_name}"
    )
    assert callable(getattr(mod, "build_subagent", None)), (
        f"planner subagent module {kind.planner_subagent_name} missing build_subagent"
    )


@pytest.mark.parametrize("key", sorted(BRIEF_KINDS))
def test_doc_kind_known_to_verify(key: str) -> None:
    kind = BRIEF_KINDS[key]
    assert kind.doc_kind in _REQUIRED_HEADINGS, (
        f"verify._REQUIRED_HEADINGS missing doc_kind {kind.doc_kind!r}"
    )


@pytest.mark.parametrize("key", sorted(BRIEF_KINDS))
def test_output_path_under_briefs_prefix(key: str) -> None:
    out = briefs_output_path(key, version=1)
    head = out.split("/", 1)[0]
    assert head == "briefs"
    assert head in WRITABLE_PREFIXES


def test_briefs_output_path_rejects_zero_or_negative_version() -> None:
    with pytest.raises(ValueError):
        briefs_output_path("civil_brief", version=0)


def test_find_kind_resolves_key_and_label() -> None:
    assert find_kind("civil_brief") is BRIEF_KINDS["civil_brief"]
    assert find_kind("민사 준비서면") is BRIEF_KINDS["civil_brief"]
    assert find_kind("not_a_kind") is None
