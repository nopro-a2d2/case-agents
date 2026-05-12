"""``skill`` tool — load a SKILL.md body on demand (progressive disclosure).

The system prompt advertises only the skill *name + description*; the model
calls this tool to fetch the full instructions when a skill applies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import tool

if TYPE_CHECKING:
    from case_agent.skills import Skill


def build_skill_tool(registry: "dict[str, Skill]"):
    names = sorted(registry)
    available = ", ".join(names) if names else "(none)"
    description = (
        "Load the full instructions for a named skill. Pass the "
        "user-provided arguments verbatim in `arguments` (or \"\" if none). "
        "After receiving the body, follow its instructions exactly — "
        "including any tool-call sequence it prescribes. "
        f"Available skills: {available}."
    )

    @tool("skill", description=description)
    def skill(name: str, arguments: str = "") -> str:
        sk = registry.get(name)
        if sk is None:
            return f"unknown skill: {name!r}\navailable: {available}"
        header = f"# Skill: {sk.name}\n\n(arguments: {arguments!r})\n\n"
        return header + sk.body

    return skill
