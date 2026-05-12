"""Slash command expansion: ``/<name> <args>`` → equivalent natural-language
prompt that nudges the model to invoke the matching skill.

Skills and slash commands share one ``SKILL.md`` registry. This helper just
rewrites the user message so the model picks up the existing ``skill`` tool
flow — no separate wire protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from case_agent.loop.types import SkillsList

if TYPE_CHECKING:
    from case_agent.commands import Command, CommandHandler
    from case_agent.skills import Skill


def build_skills_list_event(
    commands: "dict[str, tuple[Command, CommandHandler]]",
    skills: "dict[str, Skill]",
) -> SkillsList:
    """Render commands + skills into a wire-friendly :class:`SkillsList`
    event. Commands first (control plane), skills second (model plane).
    Each entry carries a ``kind`` of ``"command"`` or ``"skill"`` so the
    client can group them.
    """
    cmd_entries = tuple(
        {
            "name": c.name,
            "description": c.description,
            "argument_hint": c.argument_hint,
            "when_to_use": c.when_to_use,
            "kind": "command",
        }
        for c, _handler in sorted(commands.values(), key=lambda x: x[0].name)
    )
    skill_entries = tuple(
        {
            "name": s.name,
            "description": s.description,
            "argument_hint": s.argument_hint,
            "when_to_use": s.when_to_use,
            "kind": "skill",
        }
        for s in sorted(skills.values(), key=lambda x: x.name)
    )
    return SkillsList(skills=cmd_entries + skill_entries)


def expand_slash(prompt: str, registry: "dict[str, Skill]") -> str:
    """If ``prompt`` starts with ``/`` and names a known skill, rewrite it
    as an instruction to call that skill. Otherwise return the original.

    A leading slash with an unknown name is left untouched so the user sees
    a normal model reply (instead of a silent no-op).
    """
    if not prompt.startswith("/"):
        return prompt
    head, _, tail = prompt[1:].partition(" ")
    name = head.strip()
    if not name or name not in registry:
        return prompt
    args = tail.strip()
    if args:
        return f"Use the `{name}` skill.\n\nArguments: {args}"
    return f"Use the `{name}` skill."
