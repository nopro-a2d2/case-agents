"""Build the ``Available skills`` block appended to the main system prompt."""

from __future__ import annotations

from . import Skill

_HEADER = """## Available skills

You have access to the following named skills. To use one, call the `skill`
tool with `name=<skill_name>`; that loads the full instructions. Each line
is **listing only** — do not assume content beyond the description."""


def build_skill_listing(registry: dict[str, Skill]) -> str:
    """Return a markdown listing for the system prompt. Empty string when
    the registry is empty so callers can append unconditionally."""
    if not registry:
        return ""
    lines = [_HEADER, ""]
    for name in sorted(registry):
        sk = registry[name]
        desc = sk.description or "(no description)"
        if sk.when_to_use:
            desc = f"{desc} — {sk.when_to_use}"
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines) + "\n"
