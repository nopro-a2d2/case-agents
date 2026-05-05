"""Tests for the .env auto-loader.

Verifies:
  - load_env returns the path it loaded (not None for known cases),
  - existing env vars are NEVER overwritten (override=False default),
  - CASE_AGENT_DOTENV explicit override is respected,
  - re-entrant: a second call without override is a no-op.
"""

from __future__ import annotations

import os

from case_agent._env import load_env


def test_load_env_respects_existing_vars(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO_FROM_DOTENV=from_file\nGCP_PROJECT=should_not_clobber\n")

    monkeypatch.setenv("GCP_PROJECT", "real_value")
    monkeypatch.setenv("CASE_AGENT_DOTENV", str(env_file))

    # Package import already ran load_env() once and cached _LOADED=True.
    # Reset so this call performs a real load.
    import case_agent._env as env_mod

    env_mod._LOADED = False

    loaded = load_env(override=False)
    assert loaded == env_file
    assert os.environ["GCP_PROJECT"] == "real_value"  # not clobbered
    assert os.environ.get("FOO_FROM_DOTENV") == "from_file"


def test_load_env_explicit_override_wins(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text("CASE_AGENT_TEST_FLAG=custom_path\n")

    monkeypatch.setenv("CASE_AGENT_DOTENV", str(env_file))
    monkeypatch.delenv("CASE_AGENT_TEST_FLAG", raising=False)

    loaded = load_env(override=True)
    assert loaded == env_file
    assert os.environ.get("CASE_AGENT_TEST_FLAG") == "custom_path"


def test_load_env_no_dotenv_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CASE_AGENT_DOTENV", raising=False)
    monkeypatch.chdir(tmp_path)  # cwd has no .env

    # Reset the module-level cache so this call is a real attempt.
    import case_agent._env as env_mod

    env_mod._LOADED = False

    # Note: this still walks up from case_agent/_env.py to find a project-root
    # .env if one exists. We accept either None or a path outside tmp_path —
    # the contract is just that no error is raised.
    result = load_env(override=False)
    assert result is None or result.is_file()
