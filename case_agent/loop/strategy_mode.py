"""Strategy Mode: 5-phase planning workflow before non-trivial work.

Mirrors Claude Code's plan mode adapted to lawyer tasks (QA / 분석 / 서면).
Active state persists in ``state/strategy.json`` at the workspace root so it
survives across CLI invocations.

Enforcement is **soft** — the system prompt instructs the model to write only
into the returned ``plan_path`` while strategy mode is active. We do not block
writes at the workspace layer; the prompt + state file is the contract.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from ..workspace import Workspace


STATE_FILE = "state/strategy.json"
PLANS_DIR = "plans"
_VERSION_RE = re.compile(r"_v(\d+)\.md\Z")
_TASK_RE = re.compile(r"\A[A-Za-z0-9_\-가-힣]+\Z")

STRATEGY_FORCE_REMINDER = """
<plan-mode-active>
Plan Mode가 사용자에 의해 강제 활성화되었습니다. 다음 규칙을 반드시 따르세요:

1. 첫 행동은 `enter_strategy_mode(task="<짧은_식별자>")` 호출입니다 — 단순 질의로 보이더라도 예외 없습니다. 단, `state/strategy.json`이 이미 active이면 새 진입 대신 진행 중인 plan 파일을 이어서 갱신합니다.
2. Strategy Mode가 active인 동안에는 반환된 `plan_path`(즉 `plans/{task}_v{N}.md`) 외의 파일은 작성하지 않습니다. `artifacts/` 산출은 보류합니다.
3. 5단계(Initial Understanding → Design → Review → Final Plan → Approval)를 plan 파일 본문에 진행합니다.
4. 사용자 승인이 명시되면 `exit_strategy_mode()` 호출 후 실행 단계로 전환합니다.
</plan-mode-active>
""".strip()


@dataclass(slots=True)
class StrategyState:
    active: bool
    task: str | None = None
    plan_path: str | None = None
    version: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _validate_task(task: str) -> None:
    if not task or not _TASK_RE.match(task):
        raise ValueError(
            f"invalid task name: {task!r} "
            f"(allowed: alphanumerics, hyphen, underscore, hangul)"
        )


def read_state(workspace: Workspace) -> StrategyState:
    if not workspace.exists(STATE_FILE):
        return StrategyState(active=False)
    return StrategyState(**json.loads(workspace.read(STATE_FILE)))


def _write_state(workspace: Workspace, state: StrategyState) -> None:
    workspace.write(
        STATE_FILE,
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )


def _next_version(workspace: Workspace, task: str) -> int:
    versions: list[int] = []
    for path in workspace.glob(f"{PLANS_DIR}/{task}_v*.md"):
        m = _VERSION_RE.search(path)
        if m:
            versions.append(int(m.group(1)))
    return max(versions, default=0) + 1


def enter_strategy_mode(workspace: Workspace, task: str) -> StrategyState:
    """Begin strategy mode for ``task``. Creates a fresh plan file from template."""
    _validate_task(task)
    current = read_state(workspace)
    if current.active and current.task != task:
        raise ValueError(
            f"strategy mode already active for task={current.task!r}; "
            f"call exit_strategy_mode first"
        )

    version = _next_version(workspace, task)
    plan_path = f"{PLANS_DIR}/{task}_v{version}.md"
    workspace.write(plan_path, _plan_template(task, version))
    state = StrategyState(active=True, task=task, plan_path=plan_path, version=version)
    _write_state(workspace, state)
    return state


def exit_strategy_mode(workspace: Workspace) -> StrategyState:
    """Mark strategy mode finished after the user approved the plan."""
    current = read_state(workspace)
    if not current.active:
        raise ValueError("strategy mode is not active")
    finished = StrategyState(
        active=False,
        task=current.task,
        plan_path=current.plan_path,
        version=current.version,
    )
    _write_state(workspace, finished)
    return finished


def _plan_template(task: str, version: int) -> str:
    return f"""# Plan: {task} (v{version})

## Phase 1. Initial Understanding
사용자 요청이 무엇인지 정의·구체화. Explore 서브에이전트로 wiki·문서 탐색.

- 사건/쟁점:
- 산출물 형태(채팅 답변 / artifacts/ markdown):
- 주요 자료 위치:

## Phase 2. Design
요청 완수에 필요한 데이터·추론 단계 설계 — 변호사의 머릿속 흐름을 외화.

- 자료 수집 순서:
- Reasoning trace:
- 검토·반박·종합 흐름:

## Phase 3. Review
핵심 문서를 직접 읽고 부족한 정보·모호한 지시는 사용자에게 질의.

- 핵심 문서:
- 사용자 확인 필요 사항:

## Phase 4. Final Plan
요청 작업의 목적과 분석 방법.

- 목적:
- 분석 방법:
- 산출물 위치 / 형식:

## Phase 5. Approval
사용자 승인 후 `exit_strategy_mode` 호출하여 실행 단계로 진입.
"""
