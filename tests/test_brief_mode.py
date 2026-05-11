"""Brief Mode state machine + tool wrappers."""

from __future__ import annotations

import json

import pytest

from case_agent.loop import brief_mode, runner, strategy_mode
from case_agent.tools.brief import (
    build_approve_brief_outline_tool,
    build_enter_brief_mode_tool,
    build_exit_brief_mode_tool,
    build_propose_brief_outline_tool,
    build_read_brief_mode_tool,
    build_write_brief_section_tool,
)
from case_agent.tools.todos import TodoStore
from case_agent.workspace import LocalFS

CASE_ID = "spark"


@pytest.fixture()
def ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


@pytest.fixture(autouse=True)
def _reset_modes(ws: LocalFS) -> None:
    """Ensure clean state before/after each test (brief.json + strategy.json)."""
    if ws.exists(brief_mode.STATE_FILE):
        ws.write(
            brief_mode.STATE_FILE,
            json.dumps(brief_mode.BriefModeState(active=False).to_dict()) + "\n",
        )
    if ws.exists(strategy_mode.STATE_FILE):
        ws.write(
            strategy_mode.STATE_FILE,
            json.dumps(strategy_mode.StrategyState(active=False).to_dict()) + "\n",
        )
    yield
    if ws.exists(brief_mode.STATE_FILE):
        ws.write(
            brief_mode.STATE_FILE,
            json.dumps(brief_mode.BriefModeState(active=False).to_dict()) + "\n",
        )


def _sections() -> list[dict]:
    return [
        {"id": "1", "title": "청구취지", "summary": "원고 청구 요지.", "evidence_hints": ["json/1.json#p1"]},
        {"id": "2", "title": "주장", "summary": "쟁점별 주장.", "evidence_hints": []},
        {"id": "3", "title": "결론", "summary": "청구 인용 구함.", "evidence_hints": []},
    ]


# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------


def test_enter_allocates_paths_and_version(ws: LocalFS) -> None:
    state = brief_mode.enter_brief_mode(ws, "civil_brief")
    assert state.active
    assert state.kind == "civil_brief"
    assert state.task == f"brief_civil_brief_v{state.version}"
    assert state.outline_path == f"briefs/{state.task}_outline.md"
    assert state.output_path == f"briefs/civil_brief_v{state.version}.md"
    assert state.context_path == f"briefs/{state.task}_context.md"
    assert state.phase == "outline"
    assert state.sections == []
    assert state.case_summary == ""
    assert state.strategy_direction == ""


def test_enter_resolves_korean_label(ws: LocalFS) -> None:
    state = brief_mode.enter_brief_mode(ws, "민사 준비서면")
    assert state.kind == "civil_brief"


def test_enter_idempotent_for_same_kind(ws: LocalFS) -> None:
    s1 = brief_mode.enter_brief_mode(ws, "civil_brief")
    s2 = brief_mode.enter_brief_mode(ws, "civil_brief")
    assert s1.task == s2.task
    assert s1.version == s2.version


def test_enter_rejects_other_kind_while_active(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    with pytest.raises(ValueError, match="already active"):
        brief_mode.enter_brief_mode(ws, "general_brief")


def test_enter_blocked_by_active_strategy_mode(ws: LocalFS) -> None:
    strategy_mode.enter_strategy_mode(ws, "some_task")
    try:
        with pytest.raises(ValueError, match="strategy mode"):
            brief_mode.enter_brief_mode(ws, "civil_brief")
    finally:
        strategy_mode.exit_strategy_mode(ws)


def test_propose_outline_writes_markdown_and_sets_phase(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    state = brief_mode.propose_outline(
        ws,
        _sections(),
        case_summary="원고는 매매대금 청구.",
        strategy_direction="처분문서 우선 + 인부 명확화.",
        context_markdown="요건사실: 매매계약 성립 + 대금 지급 의무.",
    )
    assert state.phase == "awaiting_approval"
    assert len(state.sections) == 3
    assert ws.exists(state.outline_path)
    assert state.context_path is not None and ws.exists(state.context_path)
    body = ws.read(state.outline_path)
    assert "민사 준비서면" in body
    assert "1. 청구취지" in body
    assert "2. 주장" in body
    assert "사건 요지" in body
    assert "전략 방향" in body
    assert "원고는 매매대금 청구" in body
    assert "처분문서 우선" in body
    context_body = ws.read(state.context_path)
    assert "요건사실: 매매계약 성립" in context_body


def test_propose_outline_without_reasoning_still_works(ws: LocalFS) -> None:
    """Empty reasoning args are acceptable — fields default to empty strings."""
    brief_mode.enter_brief_mode(ws, "civil_brief")
    state = brief_mode.propose_outline(ws, _sections())
    assert state.case_summary == ""
    assert state.strategy_direction == ""
    body = ws.read(state.outline_path)
    assert "사건 요지" in body  # header present even when content empty
    assert "_(아직 작성되지 않음)_" in body


def test_state_round_trip_preserves_reasoning_fields(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(
        ws,
        _sections(),
        case_summary="요지.",
        strategy_direction="방향.",
        context_markdown="컨텍스트.",
    )
    state = brief_mode.read_state(ws)
    assert state.case_summary == "요지."
    assert state.strategy_direction == "방향."
    assert state.context_path is not None


def test_propose_outline_rejects_duplicate_ids(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    with pytest.raises(ValueError, match="duplicate section id"):
        brief_mode.propose_outline(
            ws,
            [{"id": "1", "title": "A"}, {"id": "1", "title": "B"}],
        )


def test_propose_outline_rejects_invalid_section_id(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    with pytest.raises(ValueError, match="invalid section id"):
        brief_mode.propose_outline(
            ws,
            [{"id": "with/slash", "title": "X"}],
        )


def test_approve_initializes_output_and_transitions_to_drafting(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(ws, _sections())
    state = brief_mode.approve_outline(ws)
    assert state.phase == "drafting"
    assert ws.exists(state.output_path)
    body = ws.read(state.output_path)
    assert body.startswith("# 민사 준비서면")
    assert "Brief Mode" in body


def test_approve_requires_awaiting_approval(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    with pytest.raises(ValueError, match="awaiting_approval"):
        brief_mode.approve_outline(ws)


def test_append_section_appends_block_and_marks_completed(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(ws, _sections())
    brief_mode.approve_outline(ws)

    state, sec, nxt = brief_mode.append_section(ws, "1", "원고 청구 요지 본문 (json/1.json#p1).")
    assert sec.id == "1"
    assert sec.completed is True
    assert nxt is not None and nxt.id == "2"
    body = ws.read(state.output_path)
    assert "## 1. 청구취지" in body
    assert "원고 청구 요지 본문" in body


def test_append_section_unknown_id_raises(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(ws, _sections())
    brief_mode.approve_outline(ws)
    with pytest.raises(ValueError, match="unknown section id"):
        brief_mode.append_section(ws, "999", "...")


def test_append_section_double_write_raises(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(ws, _sections())
    brief_mode.approve_outline(ws)
    brief_mode.append_section(ws, "1", "first body")
    with pytest.raises(ValueError, match="already completed"):
        brief_mode.append_section(ws, "1", "second body")


def test_append_section_blocked_before_approval(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(ws, _sections())
    with pytest.raises(ValueError, match="phase=drafting"):
        brief_mode.append_section(ws, "1", "body")


def test_all_completed_yields_no_next(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(ws, _sections())
    brief_mode.approve_outline(ws)
    last_next = "sentinel"
    for sid in ("1", "2", "3"):
        _, _, last_next = brief_mode.append_section(ws, sid, f"body {sid}")
    assert last_next is None
    assert brief_mode.read_state(ws).all_completed()


def test_exit_marks_inactive(ws: LocalFS) -> None:
    brief_mode.enter_brief_mode(ws, "civil_brief")
    brief_mode.propose_outline(ws, _sections())
    brief_mode.approve_outline(ws)
    brief_mode.append_section(ws, "1", "body 1")
    state = brief_mode.exit_brief_mode(ws)
    assert state.active is False
    assert state.phase == "done"


# ---------------------------------------------------------------------------
# tool wrappers (incl. TodoStore integration)
# ---------------------------------------------------------------------------


def test_tool_flow_publishes_and_advances_todos(ws: LocalFS) -> None:
    store = TodoStore()
    enter = build_enter_brief_mode_tool(ws)
    propose = build_propose_brief_outline_tool(ws)
    approve = build_approve_brief_outline_tool(ws, store)
    write_section = build_write_brief_section_tool(ws, store)
    exit_tool = build_exit_brief_mode_tool(ws)

    enter.invoke({"kind": "civil_brief"})
    propose.invoke({"sections": _sections()})

    res = json.loads(approve.invoke({}))
    assert res["ok"]
    todos = store.snapshot()
    assert [t["status"] for t in todos] == ["in_progress", "pending", "pending"]
    assert "[1] 청구취지" in todos[0]["content"]

    res = json.loads(write_section.invoke({"section_id": "1", "content": "본문 1 (json/1.json#p1)"}))
    assert res["ok"]
    assert res["next_section"]["id"] == "2"
    assert not res["all_done"]
    todos = store.snapshot()
    assert [t["status"] for t in todos] == ["completed", "in_progress", "pending"]

    json.loads(write_section.invoke({"section_id": "2", "content": "본문 2"}))
    res = json.loads(write_section.invoke({"section_id": "3", "content": "본문 3"}))
    assert res["all_done"]
    todos = store.snapshot()
    assert all(t["status"] == "completed" for t in todos)

    res = json.loads(exit_tool.invoke({}))
    assert res["ok"]
    assert res["sections_completed"] == 3


def test_tool_unknown_kind_returns_error(ws: LocalFS) -> None:
    enter = build_enter_brief_mode_tool(ws)
    res = json.loads(enter.invoke({"kind": "nonsense_kind"}))
    assert "error" in res


def test_brief_force_reminder_mentions_enter_brief_mode() -> None:
    text = brief_mode.BRIEF_FORCE_REMINDER
    assert "<brief-mode-active>" in text
    assert "enter_brief_mode" in text
    assert "propose_brief_outline" in text
    assert "approve_brief_outline" in text
    # New: reminder must tell the agent to delegate to the planner subagent
    # and to stop after propose for user approval via UI.
    assert "planner_subagent_name" in text
    assert "context_path" in text


def test_enter_brief_mode_tool_returns_planner_name(ws: LocalFS) -> None:
    res = json.loads(build_enter_brief_mode_tool(ws).invoke({"kind": "civil_brief"}))
    assert res["planner_subagent_name"] == "brief_planning_civil"
    assert res["writer_subagent_name"] == "brief_civil"
    assert res["context_path"].endswith("_context.md")
    assert "delegate planning" in res["instructions"]


def test_propose_tool_accepts_reasoning_fields(ws: LocalFS) -> None:
    """propose_brief_outline tool wires through reasoning + context to state."""
    build_enter_brief_mode_tool(ws).invoke({"kind": "civil_brief"})
    res = json.loads(
        build_propose_brief_outline_tool(ws).invoke(
            {
                "sections": _sections(),
                "case_summary": "요지.",
                "strategy_direction": "방향.",
                "context_markdown": "법리.",
            }
        )
    )
    assert res["ok"]
    assert res["phase"] == "awaiting_approval"
    assert res["context_path"].endswith("_context.md")
    state = brief_mode.read_state(ws)
    assert state.case_summary == "요지."
    assert state.strategy_direction == "방향."


def test_runner_imports_brief_force_reminder() -> None:
    """runner.py wires force_brief → BRIEF_FORCE_REMINDER as system_extra."""
    assert runner.BRIEF_FORCE_REMINDER is brief_mode.BRIEF_FORCE_REMINDER


def test_read_brief_mode_tool_reflects_state(ws: LocalFS) -> None:
    store = TodoStore()
    build_enter_brief_mode_tool(ws).invoke({"kind": "civil_brief"})
    build_propose_brief_outline_tool(ws).invoke({"sections": _sections()})
    build_approve_brief_outline_tool(ws, store).invoke({})
    res = json.loads(build_read_brief_mode_tool(ws).invoke({}))
    assert res["active"] is True
    assert res["phase"] == "drafting"
    assert len(res["sections"]) == 3
