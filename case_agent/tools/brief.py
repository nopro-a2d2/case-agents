"""LangChain tools for Brief Mode (서면 작성 모드).

Wraps the state-machine functions in :mod:`case_agent.loop.brief_mode` and
keeps the per-section TodoStore in sync. Tools live behind a single factory
:func:`build_brief_mode_tools` that captures the workspace + todo store via
closure, mirroring how :mod:`.strategy` exposes Strategy Mode.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from langchain_core.tools import tool

from ..briefs import BRIEF_KINDS
from ..loop import brief_mode
from ..workspace import Workspace
from .todos import TodoStore


# ---------------------------------------------------------------------------
# todo helpers
# ---------------------------------------------------------------------------


def _todo_content(section: brief_mode.BriefSection) -> str:
    return f"[{section.id}] {section.title} 작성"


def _publish_todos_for_drafting(
    state: brief_mode.BriefModeState,
    todos_store: TodoStore,
) -> list[dict]:
    """Replace the visible todo list with one entry per outline section.

    First incomplete becomes ``in_progress``; the rest ``pending``. Already
    completed sections become ``completed``. Returns the new todo list.
    """
    todos: list[dict] = []
    in_progress_assigned = False
    for sec in state.sections:
        if sec.completed:
            todos.append({"content": _todo_content(sec), "status": "completed"})
            continue
        if not in_progress_assigned:
            todos.append({"content": _todo_content(sec), "status": "in_progress"})
            in_progress_assigned = True
        else:
            todos.append({"content": _todo_content(sec), "status": "pending"})
    todos_store.replace(todos)  # type: ignore[arg-type]
    return todos


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


def build_enter_brief_mode_tool(workspace: Workspace):
    @tool
    def enter_brief_mode(kind: str) -> str:
        """Enter Brief Mode for a specific 서면 종류.

        Brief Mode is the dedicated workflow for drafting a 서면. It works in
        three phases: outline → awaiting_approval → drafting. The model
        proposes an outline, the user approves it, then the brief is written
        section by section. This is **the only path** for 서면 작성 — do not
        use Strategy Mode for briefs.

        WHEN to call:
          - 사용자가 서면 작성을 요청. 명시적으로 "민사 준비서면" 요청이면
            ``civil_brief``, 그 외 모든 서면(답변서·항소이유서·의견서·보충서 등)
            과 종류가 모호한 경우는 ``general_brief``.
          - 단순 조회·분석 요청에는 호출하지 말 것.

        After this returns, delegate planning to the kind's planner subagent.
        For ``general_brief`` the planner may respond with ``phase=="asking"``
        and a ``questions`` list — surface those to the user and end the turn.

        Args:
            kind: 서면 종류 — BRIEF_KINDS 키(``civil_brief`` 또는
                ``general_brief``) 또는 한국어 라벨("민사 준비서면" / "범용 서면").

        Returns JSON ``{active, kind, task, phase, outline_path, output_path,
        version, sections_count, instructions}`` or ``{error: ...}``.
        """
        try:
            state = brief_mode.enter_brief_mode(workspace, kind)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        kind_meta = BRIEF_KINDS[state.kind]  # type: ignore[index]
        out = {
            "active": state.active,
            "kind": state.kind,
            "task": state.task,
            "phase": state.phase,
            "outline_path": state.outline_path,
            "output_path": state.output_path,
            "context_path": state.context_path,
            "version": state.version,
            "sections_count": len(state.sections),
            "planner_subagent_name": kind_meta.planner_subagent_name,
            "writer_subagent_name": kind_meta.subagent_name,
            "instructions": (
                f"Next: delegate planning to the kind-specific planner subagent. "
                f"Call task(subagent_name={kind_meta.planner_subagent_name!r}, "
                f"prompt=<사용자 원문 + 사건 메타 + outline_path={state.outline_path!r} "
                f"+ context_path={state.context_path!r}>). The planner returns a JSON "
                f"object with case_summary / strategy_direction / sections / "
                f"context_markdown — pass those fields verbatim to "
                f"propose_brief_outline(...). After propose returns, STOP and let "
                f"the user approve via UI."
            ),
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    return enter_brief_mode


def build_propose_brief_outline_tool(workspace: Workspace):
    @tool
    def propose_brief_outline(
        sections: list[dict],
        case_summary: str = "",
        strategy_direction: str = "",
        context_markdown: str = "",
    ) -> str:
        """Propose the section outline + writer context for the active brief.

        **Before calling**, delegate to the kind-specific
        ``brief_planning_<kind>`` subagent via ``task(...)`` and pass its
        returned JSON fields verbatim. Do NOT fabricate the outline yourself —
        the planner subagent's role is to reason about 사건 요지, 전략 방향,
        and TOC before drafting begins.

        Args:
            sections: Ordered list. Each entry:
                - ``id`` (required): stable identifier — alphanumerics / hangul /
                  ``- _ .`` only; 1~32 chars (e.g. ``"1"``, ``"2-가"``).
                - ``title`` (required): 섹션 제목 (e.g. ``"청구취지"``).
                - ``summary`` (optional but recommended): 1~3문장으로 섹션에
                  들어갈 내용 요약.
                - ``evidence_hints`` (optional): 인용 후보 ``@@[id]`` 리스트.
            case_summary: 2~5문장 사건 요지 (사용자에게 표시).
            strategy_direction: 2~4문장 설득 논리 흐름 (사용자에게 표시).
            context_markdown: 법리 검토 / 문체 지침 — writer 전용. 별도 파일
                ``context_path`` 에 저장되며 사용자 outline UI에는 표시되지 않는다.

        Side effects:
            Writes outline to ``state.outline_path`` (사건 요지 + 전략 방향 + 목차)
            and context to ``state.context_path`` (writer 전용). Phase transitions
            to ``awaiting_approval``.

        **After this returns, STOP** — the user approves via UI. Do not call
        approve_brief_outline yourself; wait for the user's "[사용자 승인됨]"
        message.

        Returns JSON ``{ok, outline_path, context_path, sections_count, phase}``
        or ``{error: ...}``.
        """
        try:
            state = brief_mode.propose_outline(
                workspace,
                sections,
                case_summary=case_summary,
                strategy_direction=strategy_direction,
                context_markdown=context_markdown,
            )
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        return json.dumps(
            {
                "ok": True,
                "outline_path": state.outline_path,
                "context_path": state.context_path,
                "sections_count": len(state.sections),
                "phase": state.phase,
                "instructions": (
                    "STOP this turn. The user will review the outline via UI "
                    "(Accept / Reject / Change). approve_brief_outline() must "
                    "only be called after the user's explicit approval message."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    return propose_brief_outline


def build_approve_brief_outline_tool(workspace: Workspace, todos_store: TodoStore):
    @tool
    def approve_brief_outline() -> str:
        """Mark the outline approved and begin section-by-section drafting.

        Call this **only** after the user has explicitly approved the outline.
        Effects:
          - Phase → ``drafting``.
          - Output file initialized with a header (sections will be appended).
          - Per-section todos published: first ``in_progress``, rest ``pending``.

        After this returns, delegate the first section to the kind's brief
        subagent: ``task(subagent_name="brief_<kind>", prompt=<섹션 spec + 경로>)``.
        The subagent calls ``write_brief_section`` to append its result.

        Returns JSON ``{ok, phase, output_path, todos, next_section}`` or
        ``{error: ...}``.
        """
        try:
            state = brief_mode.approve_outline(workspace)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        todos = _publish_todos_for_drafting(state, todos_store)
        next_sec = state.sections[0] if state.sections else None
        return json.dumps(
            {
                "ok": True,
                "phase": state.phase,
                "output_path": state.output_path,
                "todos": todos,
                "next_section": asdict(next_sec) if next_sec else None,
            },
            ensure_ascii=False,
            indent=2,
        )

    return approve_brief_outline


def build_write_brief_section_tool(workspace: Workspace, todos_store: TodoStore):
    @tool
    def write_brief_section(section_id: str, content: str) -> str:
        """Append one outline section's body to the brief output file.

        Use this to commit the body of a single section while Brief Mode is in
        ``drafting`` phase. Typically called by the per-kind brief subagent
        (``brief_civil`` 등) after it finishes writing the section. The tool
        prepends ``## <id>. <title>`` automatically — do **not** include the
        section heading in ``content``.

        Side effects:
          - Reads ``state.output_path``, appends section block, writes back.
          - Marks the section ``completed`` in brief mode state.
          - Updates the visible todo list: this section ``completed``, next
            pending section ``in_progress``.

        Args:
            section_id: outline 항목의 ``id``. propose_brief_outline 에 등록된
                것과 정확히 일치해야 한다.
            content: 섹션 본문 markdown (헤딩 제외). 인용은 ``@@[id]``
                형식으로 인라인 부착.

        Returns JSON ``{ok, written_to, section_id, next_section, all_done}``
        or ``{error: ...}``.
        """
        try:
            state, sec, next_section = brief_mode.append_section(
                workspace, section_id, content
            )
        except (ValueError, FileNotFoundError) as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        # Re-publish todos to reflect the completion + next in_progress.
        _publish_todos_for_drafting(state, todos_store)
        return json.dumps(
            {
                "ok": True,
                "written_to": state.output_path,
                "section_id": sec.id,
                "next_section": asdict(next_section) if next_section else None,
                "all_done": next_section is None,
            },
            ensure_ascii=False,
            indent=2,
        )

    return write_brief_section


def build_exit_brief_mode_tool(workspace: Workspace):
    @tool
    def exit_brief_mode() -> str:
        """End Brief Mode after every section is completed.

        Call this only when ``write_brief_section`` returned ``all_done=True``.
        After exit, run ``verify_citations(output_path)`` and
        ``check_completeness(<kind>, output_path)`` on the assembled brief
        before reporting to the user.

        Returns JSON ``{ok, output_path, sections_completed, exited}``
        or ``{error: ...}``.
        """
        try:
            state = brief_mode.exit_brief_mode(workspace)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        completed = sum(1 for s in state.sections if s.completed)
        return json.dumps(
            {
                "ok": True,
                "output_path": state.output_path,
                "sections_completed": completed,
                "sections_total": len(state.sections),
                "exited": True,
            },
            ensure_ascii=False,
            indent=2,
        )

    return exit_brief_mode


def build_read_brief_mode_tool(workspace: Workspace):
    @tool
    def read_brief_mode() -> str:
        """Read the current Brief Mode state (debug / recovery).

        Useful when the agent loses context and needs to figure out which
        section is in progress. Returns the full state JSON.
        """
        state = brief_mode.read_state(workspace)
        return json.dumps(state.to_dict(), ensure_ascii=False, indent=2)

    return read_brief_mode


def build_brief_mode_tools(
    workspace: Workspace,
    todos_store: TodoStore,
) -> list[Any]:
    """Return every Brief Mode tool, in the order the system prompt references."""
    return [
        build_enter_brief_mode_tool(workspace),
        build_propose_brief_outline_tool(workspace),
        build_approve_brief_outline_tool(workspace, todos_store),
        build_write_brief_section_tool(workspace, todos_store),
        build_exit_brief_mode_tool(workspace),
        build_read_brief_mode_tool(workspace),
    ]


__all__ = ["build_brief_mode_tools"]
