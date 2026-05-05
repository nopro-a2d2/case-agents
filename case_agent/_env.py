"""Auto-load .env once per process (idempotent).

Search order (first hit wins):
    1. $CASE_AGENT_DOTENV  (explicit override)
    2. $PWD/.env           (cwd at import-time)
    3. nearest .env walking up from this file (project root in dev installs)

Existing environment variables are NEVER overwritten — `.env` only fills gaps.
This makes the CLI Just Work in development while staying safe in production
where real env vars are usually set by the deployment platform.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_LOADED = False


def load_env(*, override: bool = False) -> Path | None:
    """Locate and load a .env file. Returns the path that was loaded, or None.

    Re-entrant: subsequent calls are no-ops unless `override=True`.
    """
    global _LOADED
    if _LOADED and not override:
        return None

    # 1) explicit override
    explicit = os.environ.get("CASE_AGENT_DOTENV")
    if explicit and Path(explicit).is_file():
        load_dotenv(explicit, override=override)
        _LOADED = True
        return Path(explicit)

    # 2) cwd .env
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        load_dotenv(cwd_env, override=override)
        _LOADED = True
        return cwd_env

    # 3) walk up from this file (handles `uv run` from project root)
    here = Path(__file__).resolve().parent
    for parent in (here, *here.parents):
        cand = parent / ".env"
        if cand.is_file():
            load_dotenv(cand, override=override)
            _LOADED = True
            return cand

    return None
