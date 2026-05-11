"""Brief (서면) registry — single source of truth for legal-document drafting.

Every supported brief kind is declared here as a :class:`BriefKind`. Subagents,
SKILL.md files, the verify checklist, and the output-path helper all dereference
this registry, so adding a new brief type is a single-file change here plus the
matching subagent / SKILL.md / verify rule.

Brief structure varies enough by case that there is no fixed packaged template;
section composition comes from the strategy plan and the per-kind subagent's
system prompt. See ``case_agent/subagents/brief_*.py`` and the bundled
``skills/bundled/brief_*`` SKILL.md files for the structural guidance.
"""

from __future__ import annotations

from dataclasses import dataclass

_BRIEFS_DIR = "briefs"


@dataclass(frozen=True, slots=True)
class BriefKind:
    """Static descriptor for a supported brief type.

    ``key`` matches the verify ``DocKind`` literal, the ``brief_<suffix>``
    writing subagent module name, and the SKILL.md filename. ``label_ko``
    is the user-facing Korean label (used in skill descriptions and error
    messages). ``planner_subagent_name`` is the matching ``brief_planning_<suffix>``
    that designs the outline before drafting. ``doc_kind`` defaults to ``key``
    and only needs to be set when the verify rule key diverges from the
    registry key.
    """

    key: str
    label_ko: str
    subagent_name: str
    doc_kind: str = ""  # must match verify._REQUIRED_HEADINGS keys; defaults to key
    planner_subagent_name: str = ""

    def __post_init__(self) -> None:
        if not self.doc_kind:
            object.__setattr__(self, "doc_kind", self.key)


BRIEF_KINDS: dict[str, BriefKind] = {
    "civil_brief": BriefKind(
        key="civil_brief",
        label_ko="민사 준비서면",
        subagent_name="brief_civil",
        planner_subagent_name="brief_planning_civil",
    ),
    "general_brief": BriefKind(
        key="general_brief",
        label_ko="범용 서면",
        subagent_name="brief_general",
        planner_subagent_name="brief_planning_general",
    ),
}


def briefs_output_path(kind_key: str, version: int = 1) -> str:
    """Workspace-relative output path for a brief draft, e.g. ``briefs/civil_brief_v1.md``."""
    if version < 1:
        raise ValueError(f"version must be >= 1, got {version}")
    if kind_key not in BRIEF_KINDS:
        raise KeyError(kind_key)
    return f"{_BRIEFS_DIR}/{kind_key}_v{version}.md"


def find_kind(query: str) -> BriefKind | None:
    """Resolve a free-form key or Korean label to a :class:`BriefKind`.

    Used by the brief_draft skill / main agent when classifying a user request.
    Matching is exact on ``key`` first, then exact on ``label_ko``.
    """
    if query in BRIEF_KINDS:
        return BRIEF_KINDS[query]
    for k in BRIEF_KINDS.values():
        if k.label_ko == query:
            return k
    return None


__all__ = [
    "BRIEF_KINDS",
    "BriefKind",
    "briefs_output_path",
    "find_kind",
]
