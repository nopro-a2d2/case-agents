"""SKILL.md parser. Format mirrors DeepAgents / claude-code:

```
---
name: <slug>
description: <≤1024 chars one-liner>
when_to_use: <optional>
allowed-tools: tool_a, tool_b   # or YAML list
argument-hint: <free text>
---

<body — markdown instructions>
```

Both ``allowed-tools`` (claude-code spelling) and ``allowed_tools`` are accepted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter

from . import Skill

DESCRIPTION_MAX = 1024


def _coerce_tools(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, str):
        return tuple(s.strip() for s in raw.split(",") if s.strip())
    if isinstance(raw, (list, tuple)):
        return tuple(str(s).strip() for s in raw if str(s).strip())
    return ()


def parse_skill_md(path: Path) -> Skill | None:
    """Parse one ``SKILL.md`` file. Returns ``None`` if frontmatter ``name``
    is missing — the caller logs and skips."""
    post = frontmatter.load(path)
    fm: dict[str, Any] = dict(post.metadata or {})
    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    description = str(fm.get("description") or "").strip()[:DESCRIPTION_MAX]
    when_to_use = str(fm.get("when_to_use") or fm.get("whenToUse") or "").strip()
    allowed = _coerce_tools(fm.get("allowed-tools") or fm.get("allowed_tools"))
    argument_hint = str(fm.get("argument-hint") or fm.get("argument_hint") or "").strip()
    return Skill(
        name=name.strip(),
        description=description,
        body=post.content.strip(),
        path=path.resolve(),
        when_to_use=when_to_use,
        allowed_tools=allowed,
        argument_hint=argument_hint,
        metadata={k: v for k, v in fm.items() if k not in {
            "name", "description", "when_to_use", "whenToUse",
            "allowed-tools", "allowed_tools", "argument-hint", "argument_hint",
        }},
    )


def iter_skill_files(root: Path) -> list[Path]:
    """Return all ``SKILL.md`` files under ``root``. Empty list if root missing."""
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("SKILL.md") if p.is_file())
