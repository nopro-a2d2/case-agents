"""LangChain tool wrappers for :mod:`case_agent.loop.strategy_mode`.

Two tools — ``enter_strategy_mode`` and ``exit_strategy_mode`` — that bracket
the 5-phase planning workflow. Enforcement of "edit only the plan file" is
soft (system-prompt level), the same way Claude Code's plan mode operates.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from case_agent.loop.strategy_mode import enter_strategy_mode as _enter
from case_agent.loop.strategy_mode import exit_strategy_mode as _exit
from case_agent.workspace import Workspace


def build_enter_strategy_mode_tool(workspace: Workspace):
    @tool
    def enter_strategy_mode(task: str) -> str:
        """Enter Strategy Mode — a 5-phase planning workflow before non-trivial work.

        Phases (write progressively into the returned ``plan_path``):
          1. **Initial Understanding** — define & specify the user's request.
             Use the ``task("explore", ...)`` subagent to scan wiki/docs.
          2. **Design** — design the data and reasoning steps required to
             complete the request (변호사의 업무 흐름을 외화).
          3. **Review** — read the critical docs directly; AskUser for any
             missing or ambiguous information.
          4. **Final Plan** — purpose, analysis method, output location.
          5. **Approval** — present the plan and call ``exit_strategy_mode``
             once the user approves.

        WHEN to use:
          - 다중 단계 분석·서면 작성 (요청 정의가 필요한 작업)
          - 사용자가 정확한 자료·접근을 합의해 주길 원하는 작업

        WHEN NOT to use:
          - 단순 사실 질의 (``smart_search`` 한 번이면 끝나는 것)
          - artifacts/ 의 한 줄 수정
          - 이미 plan 이 존재하고 그대로 실행하면 되는 경우

        While Strategy Mode is active, write **only** into the returned
        ``plan_path``. Do not produce ``artifacts/`` outputs until
        ``exit_strategy_mode`` is called.

        Args:
            task: short identifier for the work (e.g. "indictment_review",
                  "fact_verification_q3"). alphanumerics/hyphen/underscore/hangul.

        Returns JSON ``{"active": true, "task": "...", "plan_path": "...",
        "version": N}`` or ``{"error": "..."}``.
        """
        try:
            state = _enter(workspace, task)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        return json.dumps(state.to_dict(), ensure_ascii=False, indent=2)

    return enter_strategy_mode


def build_exit_strategy_mode_tool(workspace: Workspace):
    @tool
    def exit_strategy_mode() -> str:
        """Leave Strategy Mode after the user approves the final plan.

        Call ONLY after:
          1. The user has reviewed the plan file
          2. The user explicitly approved (or asked you to proceed)

        After exit, normal artifact production resumes — write to
        ``artifacts/`` as usual. Returns JSON describing the finalized plan,
        or ``{"error": "..."}`` if strategy mode wasn't active.
        """
        try:
            state = _exit(workspace)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        return json.dumps(state.to_dict(), ensure_ascii=False, indent=2)

    return exit_strategy_mode


def build_strategy_tools(workspace: Workspace) -> list[Any]:
    return [
        build_enter_strategy_mode_tool(workspace),
        build_exit_strategy_mode_tool(workspace),
    ]
