"""Brief Mode: outline → approval → section-by-section drafting workflow.

Parallel concept to :mod:`case_agent.loop.strategy_mode`, but specialized for
서면 작성 (legal brief drafting). Drafting is broken into discrete sections
that the main agent processes one at a time, mirroring minsa-written-ai's
``BriefWritingAgent.generate_brief`` per-turn section loop
(``app/agents/writing/brief_writing_agent.py:493-535``).

State persists in ``state/brief.json`` so it survives across CLI invocations.
Enforcement is **soft** — the system prompt instructs the model how to use
the tools; the workspace layer does not block other writes while active.

Phases:
    outline           — entered, sections not yet proposed (or being revised)
    awaiting_approval — propose_outline called; waiting for user to approve
    drafting          — approved; sections being written one by one
    done              — exit_brief_mode called; state.active = False
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from case_agent.briefs import BRIEF_KINDS, briefs_output_path, find_kind
from case_agent.loop import strategy_mode
from case_agent.workspace import Workspace

STATE_FILE = "state/brief.json"
BRIEFS_DIR = "briefs"

BriefPhase = Literal["outline", "awaiting_approval", "drafting", "done"]

BRIEF_FORCE_REMINDER = """
<brief-mode-active>
Brief Mode가 사용자에 의해 강제 활성화되었습니다. 다음 규칙을 반드시 따르세요:

1. 사용자 메시지에서 종류를 식별합니다 — 사용자가 명시적으로 "민사 준비서면"을 요청한 경우만 `civil_brief`, 그 외 모든 서면(답변서·항소이유서·보충서·의견서·반박서면 등)과 종류가 모호한 경우는 `general_brief`. **모호하면 사용자에게 다시 묻지 말고 `general_brief`로 진입**합니다 — planner가 직접 사용자에게 종류를 묻도록 설계되어 있습니다.
2. 종류 식별 직후 `enter_brief_mode(kind=<key 또는 라벨>)`를 호출합니다. 단, `state/brief.json`이 이미 같은 kind로 active이면 새 진입 대신 진행 중 outline을 이어서 갱신합니다.
3. enter_brief_mode 반환 JSON의 `planner_subagent_name`(`brief_planning_civil` 또는 `brief_planning_general`)을 그대로 `task(subagent_name=..., prompt=<사용자 원문 + outline_path/context_path 경로>)`에 넘겨 위임합니다. 메인이 직접 sections를 만들지 마세요 — 반드시 planner subagent의 JSON 응답을 사용합니다.
4. planner final message JSON의 `phase` 키를 확인합니다.
   - `phase=="asking"` (`general_brief` 한정): `questions` 배열을 사용자에게 **그대로 출력하고 턴을 종료**합니다. 추가 도구 호출 금지. 사용자 답변이 오면 같은 planner를 재호출(prompt에 원래 요청 + 누적 Q&A 포함).
   - `phase=="ready"` 또는 `phase` 키가 없는 outline JSON: 5단계로 진행.
   - `civil_brief` planner는 단발 outline JSON만 반환합니다 (phase 분기 불필요).
5. `propose_brief_outline(...)` 호출 — planner JSON의 `case_summary` / `strategy_direction` / `sections` / `context_markdown` 네 필드를 그대로 전달.
6. propose_brief_outline 호출 직후 **턴을 종료**합니다. 사용자 승인 UI가 표시됩니다. 그 어떤 추가 도구 호출도 금지 — `approve_brief_outline`은 사용자가 "[사용자 승인됨]" 메시지를 보낸 후에만 호출합니다.
7. 승인 메시지를 받으면 `approve_brief_outline()` → 섹션 단위 `task("brief_<kind>", prompt=<섹션 spec + outline_path + context_path + output_path>)` 위임 → 응답을 `write_brief_section(section_id, content)`로 append → 모든 섹션 완료 시 `exit_brief_mode()` → `verify_citations` + `check_completeness`.
8. Brief Mode가 active인 동안에는 `briefs/<task>_outline.md`, `briefs/<task>_context.md`, `briefs/<kind>_v<N>.md` 외의 파일은 작성하지 않습니다.
9. Strategy Mode 진입은 금지 — Brief Mode와 동시 활성될 수 없습니다.
</brief-mode-active>
""".strip()

_VERSION_RE = re.compile(r"_v(\d+)\.md\Z")
_SECTION_ID_RE = re.compile(r"\A[A-Za-z0-9가-힣\-_.]{1,32}\Z")


@dataclass(slots=True)
class BriefSection:
    """One outline entry. ``completed`` is flipped by ``complete_section``."""

    id: str
    title: str
    summary: str
    evidence_hints: list[str] = field(default_factory=list)
    completed: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "BriefSection":
        return cls(
            id=d["id"],
            title=d["title"],
            summary=d.get("summary", ""),
            evidence_hints=list(d.get("evidence_hints") or []),
            completed=bool(d.get("completed", False)),
        )


@dataclass(slots=True)
class BriefModeState:
    active: bool
    kind: str | None = None
    task: str | None = None
    phase: BriefPhase = "outline"
    outline_path: str | None = None
    output_path: str | None = None
    context_path: str | None = None
    version: int = 0
    sections: list[BriefSection] = field(default_factory=list)
    case_summary: str = ""
    strategy_direction: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BriefModeState":
        return cls(
            active=bool(d.get("active", False)),
            kind=d.get("kind"),
            task=d.get("task"),
            phase=d.get("phase", "outline"),
            outline_path=d.get("outline_path"),
            output_path=d.get("output_path"),
            context_path=d.get("context_path"),
            version=int(d.get("version", 0)),
            sections=[BriefSection.from_dict(s) for s in (d.get("sections") or [])],
            case_summary=str(d.get("case_summary", "")),
            strategy_direction=str(d.get("strategy_direction", "")),
        )

    def find_section(self, section_id: str) -> BriefSection | None:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None

    def all_completed(self) -> bool:
        return bool(self.sections) and all(s.completed for s in self.sections)


# ---------------------------------------------------------------------------
# state I/O
# ---------------------------------------------------------------------------


def read_state(workspace: Workspace) -> BriefModeState:
    try:
        raw = workspace.read(STATE_FILE)
    except FileNotFoundError:
        return BriefModeState(active=False)
    return BriefModeState.from_dict(json.loads(raw))


def _write_state(workspace: Workspace, state: BriefModeState) -> None:
    workspace.write(
        STATE_FILE,
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _resolve_kind_key(kind_input: str) -> str:
    """Accept either a BRIEF_KINDS key or a Korean label."""
    bk = find_kind(kind_input)
    if bk is None:
        valid = ", ".join(sorted(BRIEF_KINDS))
        raise ValueError(
            f"unknown brief kind: {kind_input!r}. Valid keys: {valid}"
        )
    return bk.key


def _next_version(workspace: Workspace, kind_key: str) -> int:
    versions: list[int] = []
    for path in workspace.glob(f"{BRIEFS_DIR}/{kind_key}_v*.md"):
        m = _VERSION_RE.search(path)
        if m:
            versions.append(int(m.group(1)))
    return max(versions, default=0) + 1


def _outline_path(task: str) -> str:
    return f"{BRIEFS_DIR}/{task}_outline.md"


def _context_path(task: str) -> str:
    return f"{BRIEFS_DIR}/{task}_context.md"


def _validate_section_id(sid: str) -> None:
    if not sid or not _SECTION_ID_RE.match(sid):
        raise ValueError(
            f"invalid section id: {sid!r} (allowed: alphanumerics, hangul, "
            f"hyphen, underscore, dot; 1-32 chars)"
        )


def _label_ko(state: BriefModeState) -> str:
    return BRIEF_KINDS[state.kind].label_ko  # type: ignore[index]


def _render_outline_md(state: BriefModeState) -> str:
    label_ko = _label_ko(state)
    lines: list[str] = [
        f"# {label_ko} 작성 계획 (v{state.version})",
        "",
        f"task: `{state.task}`  | 출력: `{state.output_path}`  | 작성 모드: Brief Mode",
        "",
        "## 사건 요지",
        "",
        state.case_summary.strip() or "_(아직 작성되지 않음)_",
        "",
        "## 전략 방향",
        "",
        state.strategy_direction.strip() or "_(아직 작성되지 않음)_",
        "",
        "## 목차",
        "",
    ]
    for sec in state.sections:
        lines.append(f"### {sec.id}. {sec.title}")
        if sec.summary:
            lines.append(f"- 요약: {sec.summary}")
        if sec.evidence_hints:
            lines.append("- 인용 자료: " + ", ".join(sec.evidence_hints))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_context_md(state: BriefModeState, context_markdown: str) -> str:
    label_ko = _label_ko(state)
    header = (
        f"# {label_ko} 작성 컨텍스트 (v{state.version})\n\n"
        f"<!-- writer 전용. 사용자에게 직접 표시되지 않으며 "
        f"brief_{state.kind} 서브에이전트가 작성 시 참조한다. -->\n\n"
    )
    body = context_markdown.strip() or "_(planner가 컨텍스트를 제공하지 않았습니다.)_"
    return header + body + "\n"


def _initial_output_body(state: BriefModeState) -> str:
    label_ko = _label_ko(state)
    return (
        f"# {label_ko}\n\n"
        f"<!-- Brief Mode {state.task} — sections will be appended in order -->\n"
    )


# ---------------------------------------------------------------------------
# transitions
# ---------------------------------------------------------------------------


def enter_brief_mode(workspace: Workspace, kind: str) -> BriefModeState:
    """Begin brief mode for ``kind``. Allocates next version and paths."""
    kind_key = _resolve_kind_key(kind)

    current = read_state(workspace)
    if current.active and current.kind != kind_key:
        raise ValueError(
            f"brief mode already active for kind={current.kind!r} "
            f"(task={current.task!r}); call exit_brief_mode first"
        )
    if strategy_mode.read_state(workspace).active:
        raise ValueError(
            "strategy mode is currently active; exit_strategy_mode first"
        )
    if current.active and current.kind == kind_key:
        # Idempotent re-entry — return existing state untouched.
        return current

    version = _next_version(workspace, kind_key)
    task = f"brief_{kind_key}_v{version}"
    state = BriefModeState(
        active=True,
        kind=kind_key,
        task=task,
        phase="outline",
        outline_path=_outline_path(task),
        output_path=briefs_output_path(kind_key, version=version),
        context_path=_context_path(task),
        version=version,
        sections=[],
    )
    _write_state(workspace, state)
    return state


def propose_outline(
    workspace: Workspace,
    sections: list[dict],
    *,
    case_summary: str = "",
    strategy_direction: str = "",
    context_markdown: str = "",
) -> BriefModeState:
    """Set the outline and writer context. ``sections`` is a list of dicts with
    id/title/summary and optional ``evidence_hints``. Replaces any prior outline.

    ``case_summary`` (2~5문장 사건 요지) and ``strategy_direction`` (2~4문장 설득
    논리 흐름) are written into the user-facing outline file. ``context_markdown``
    (법리 검토 / 문체 지침) is written to a separate ``context_path`` for the
    writer subagent to consult — it is not part of the outline shown to the user.
    """
    state = read_state(workspace)
    if not state.active:
        raise ValueError("brief mode is not active; call enter_brief_mode first")
    if state.phase == "drafting":
        raise ValueError(
            "cannot revise outline after approval; exit and re-enter to start over"
        )

    parsed: list[BriefSection] = []
    seen_ids: set[str] = set()
    for s in sections:
        if not isinstance(s, dict):
            raise ValueError(f"section entry must be a dict, got {type(s).__name__}")
        sid = str(s.get("id", "")).strip()
        title = str(s.get("title", "")).strip()
        if not title:
            raise ValueError(f"section missing 'title': {s}")
        _validate_section_id(sid)
        if sid in seen_ids:
            raise ValueError(f"duplicate section id: {sid!r}")
        seen_ids.add(sid)
        parsed.append(
            BriefSection(
                id=sid,
                title=title,
                summary=str(s.get("summary", "")).strip(),
                evidence_hints=[str(h) for h in (s.get("evidence_hints") or [])],
            )
        )
    if not parsed:
        raise ValueError("at least one section is required")

    state.sections = parsed
    state.case_summary = case_summary.strip()
    state.strategy_direction = strategy_direction.strip()
    state.phase = "awaiting_approval"
    if state.context_path is None:
        state.context_path = _context_path(state.task)  # type: ignore[arg-type]
    workspace.write(state.outline_path, _render_outline_md(state))  # type: ignore[arg-type]
    workspace.write(state.context_path, _render_context_md(state, context_markdown))
    _write_state(workspace, state)
    return state


def approve_outline(workspace: Workspace) -> BriefModeState:
    """User has reviewed and approved the outline. Initialize the output file
    with a header and transition to drafting."""
    state = read_state(workspace)
    if not state.active:
        raise ValueError("brief mode is not active")
    if state.phase != "awaiting_approval":
        raise ValueError(
            f"approve only valid in phase=awaiting_approval (current: {state.phase})"
        )
    if not state.sections:
        raise ValueError("cannot approve empty outline")

    workspace.write(state.output_path, _initial_output_body(state))  # type: ignore[arg-type]
    state.phase = "drafting"
    _write_state(workspace, state)
    return state


def append_section(
    workspace: Workspace,
    section_id: str,
    content: str,
) -> tuple[BriefModeState, BriefSection, BriefSection | None]:
    """Append one section's body to the output file and mark it completed.

    Returns ``(updated_state, completed_section, next_section_or_none)``.
    The next section is the first remaining ``completed=False`` after this
    one in declaration order, or ``None`` if all are done.
    """
    state = read_state(workspace)
    if not state.active:
        raise ValueError("brief mode is not active")
    if state.phase != "drafting":
        raise ValueError(
            f"write_brief_section requires phase=drafting (current: {state.phase}); "
            f"call approve_brief_outline first"
        )

    sec = state.find_section(section_id)
    if sec is None:
        valid = ", ".join(s.id for s in state.sections)
        raise ValueError(f"unknown section id: {section_id!r}. Valid: {valid}")
    if sec.completed:
        raise ValueError(f"section {section_id!r} is already completed")

    body = content.strip()
    if not body:
        raise ValueError("section content is empty")

    existing = workspace.read(state.output_path)  # type: ignore[arg-type]
    block = f"\n## {sec.id}. {sec.title}\n\n{body}\n"
    if not existing.endswith("\n"):
        existing += "\n"
    workspace.write(state.output_path, existing + block)  # type: ignore[arg-type]

    sec.completed = True
    next_section: BriefSection | None = None
    for s in state.sections:
        if not s.completed:
            next_section = s
            break

    # Phase stays "drafting" until exit_brief_mode is called explicitly.
    _write_state(workspace, state)
    return state, sec, next_section


def exit_brief_mode(workspace: Workspace) -> BriefModeState:
    """Mark brief mode finished. Does NOT verify completeness — caller does that."""
    current = read_state(workspace)
    if not current.active:
        raise ValueError("brief mode is not active")
    finished = replace(current, active=False, phase="done")
    _write_state(workspace, finished)
    return finished


__all__ = [
    "BRIEF_FORCE_REMINDER",
    "BriefModeState",
    "BriefSection",
    "STATE_FILE",
    "append_section",
    "approve_outline",
    "enter_brief_mode",
    "exit_brief_mode",
    "propose_outline",
    "read_state",
]
