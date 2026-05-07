"""Tests for case_agent.loop.strategy_mode."""

from __future__ import annotations

import pytest

from case_agent.loop.strategy_mode import (
    PLANS_DIR,
    STATE_FILE,
    enter_strategy_mode,
    exit_strategy_mode,
    read_state,
)
from case_agent.workspace import LocalFS


@pytest.fixture
def workspace(tmp_path):
    case_root = tmp_path / "case_x"
    case_root.mkdir()
    return LocalFS(case_id="case_x", root=tmp_path)


def test_initial_state_inactive(workspace):
    state = read_state(workspace)
    assert state.active is False
    assert state.task is None


def test_enter_creates_plan_file_and_state(workspace):
    state = enter_strategy_mode(workspace, "indictment_review")
    assert state.active is True
    assert state.task == "indictment_review"
    assert state.plan_path == f"{PLANS_DIR}/indictment_review_v1.md"
    assert state.version == 1

    # plan file initialized with template
    assert workspace.exists(state.plan_path)
    content = workspace.read(state.plan_path)
    assert "Phase 1. Initial Understanding" in content
    assert "Phase 5. Approval" in content
    assert "indictment_review" in content

    # state persisted
    assert workspace.exists(STATE_FILE)
    persisted = read_state(workspace)
    assert persisted.active is True
    assert persisted.task == "indictment_review"


def test_enter_increments_version_on_reentry_for_same_task(workspace):
    enter_strategy_mode(workspace, "task_a")
    exit_strategy_mode(workspace)
    state = enter_strategy_mode(workspace, "task_a")
    assert state.version == 2
    assert state.plan_path == f"{PLANS_DIR}/task_a_v2.md"


def test_enter_blocks_when_active_with_different_task(workspace):
    enter_strategy_mode(workspace, "task_a")
    with pytest.raises(ValueError, match="already active"):
        enter_strategy_mode(workspace, "task_b")


def test_exit_clears_active(workspace):
    enter_strategy_mode(workspace, "task_a")
    finished = exit_strategy_mode(workspace)
    assert finished.active is False
    assert finished.task == "task_a"

    persisted = read_state(workspace)
    assert persisted.active is False


def test_exit_when_not_active_raises(workspace):
    with pytest.raises(ValueError, match="not active"):
        exit_strategy_mode(workspace)


def test_invalid_task_name_rejected(workspace):
    with pytest.raises(ValueError):
        enter_strategy_mode(workspace, "")
    with pytest.raises(ValueError):
        enter_strategy_mode(workspace, "bad/name")
    with pytest.raises(ValueError):
        enter_strategy_mode(workspace, "..")


def test_korean_task_name_allowed(workspace):
    state = enter_strategy_mode(workspace, "공소장분석")
    assert state.task == "공소장분석"
    assert workspace.exists(state.plan_path)
