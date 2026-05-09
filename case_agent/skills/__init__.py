"""Skills registry.

Add a skill by dropping a directory under one of the discover roots:

```
<root>/<skill_name>/SKILL.md
```

`SKILL.md` carries YAML frontmatter (`name`, `description`, optional
`when_to_use`, `allowed-tools`, `argument-hint`). The body holds the
instructions the model loads when the skill is invoked.

Two roots are scanned by default:

* ``case_agent/skills/bundled/`` — ships with the repo
* ``<workspace.case_root>/skills/`` — per-case user skills (workspace wins
  on name collision: "last one wins").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path
    when_to_use: str = ""
    allowed_tools: tuple[str, ...] = ()
    argument_hint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def discover_skills(*roots: Path | str) -> dict[str, Skill]:
    """Walk every root for ``**/SKILL.md`` and return a name-keyed registry.

    Later roots override earlier ones on name collision (workspace beats
    bundled). Files with no ``name`` frontmatter are skipped silently.
    """
    from .loader import iter_skill_files, parse_skill_md

    out: dict[str, Skill] = {}
    for root in roots:
        rp = Path(root)
        for path in iter_skill_files(rp):
            sk = parse_skill_md(path)
            if sk is not None:
                out[sk.name] = sk
    return out


__all__ = ["Skill", "discover_skills"]
