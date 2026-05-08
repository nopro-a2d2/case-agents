"""Brief (서면) template loader and type definitions."""

from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"

BRIEF_TYPES: dict[str, str] = {
    "증거인부서": "증거인부서.md",
    "증인심문사항": "증인심문사항.md",
    "피고인심문사항": "피고인심문사항.md",
    "변호인의견서": "변호인의견서.md",
    "준비서면": "준비서면.md",
}


def load_template(brief_type: str) -> str:
    """Return the Markdown template for the given brief type name."""
    filename = BRIEF_TYPES.get(brief_type)
    if filename is None:
        raise KeyError(f"Unknown brief type: {brief_type!r}. Available: {list(BRIEF_TYPES)}")
    return (_TEMPLATES_DIR / filename).read_text(encoding="utf-8")


def list_brief_types() -> list[str]:
    return list(BRIEF_TYPES)


__all__ = ["BRIEF_TYPES", "load_template", "list_brief_types"]
