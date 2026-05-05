from pathlib import Path

_DIR = Path(__file__).parent


def _load(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")


MAIN_SYSTEM_PROMPT = _load("main_system.md")
EXPLORE_SYSTEM_PROMPT = _load("explore_system.md")

__all__ = ["MAIN_SYSTEM_PROMPT", "EXPLORE_SYSTEM_PROMPT"]
