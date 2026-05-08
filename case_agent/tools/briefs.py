"""Brief-writing tools: write_brief, load_brief_template, list_brief_templates.

Briefs are formal Korean legal documents saved to ``briefs/`` (separate from
``artifacts/``).  Templates live in ``case_agent/templates/briefs/`` and are
always Markdown.  Brief subagents load a template, fill it with evidence-backed
content, and call ``write_brief`` to persist the result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from ..workspace import Workspace

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "briefs"

_BRIEF_KINDS: dict[str, dict[str, str]] = {
    "evidence_acknowledgment": {
        "label": "증거인부서",
        "file": "증거인부서.md",
        "completeness_kind": "evidence_acknowledgment",
        "description": "검사 제출 증거에 대해 동의/부동의/일부부동의 의견을 기재하는 서면",
    },
    "witness_questions": {
        "label": "증인심문사항",
        "file": "증인심문사항.md",
        "completeness_kind": "witness_questions",
        "description": "증인 주신문 또는 반대신문을 위한 질문 목록",
    },
    "defendant_questions": {
        "label": "피고인심문사항",
        "file": "피고인심문사항.md",
        "completeness_kind": "defendant_questions",
        "description": "피고인 신문을 위한 질문 목록 (변호인 주신문)",
    },
    "defense_opinion": {
        "label": "변호인의견서",
        "file": "변호인의견서.md",
        "completeness_kind": "defense_opinion",
        "description": "사실관계·법리 검토를 포함한 변호인 공식 의견서",
    },
    "civil_brief": {
        "label": "민사준비서면",
        "file": "민사준비서면.md",
        "completeness_kind": "civil_brief",
        "description": "민사 소송에서 청구 원인·주장·반박을 기재하는 준비서면",
    },
}


def build_list_brief_templates_tool():
    @tool
    def list_brief_templates() -> str:
        """List all available Korean legal brief templates.

        Returns a JSON array describing each template kind, its Korean label,
        and the ``check_completeness`` kind string to use after writing.
        """
        import json
        result = [
            {
                "kind": kind,
                "label": info["label"],
                "completeness_kind": info["completeness_kind"],
                "description": info["description"],
            }
            for kind, info in _BRIEF_KINDS.items()
        ]
        return json.dumps(result, ensure_ascii=False, indent=2)

    return list_brief_templates


def build_load_brief_template_tool():
    @tool
    def load_brief_template(kind: str) -> str:
        """Load the Markdown template for a specific brief type.

        Args:
            kind: one of 'evidence_acknowledgment', 'witness_questions',
                  'defendant_questions', 'defense_opinion', 'civil_brief'.

        Returns the raw Markdown template text, ready to be filled in and
        saved via ``write_brief``.
        """
        if kind not in _BRIEF_KINDS:
            available = ", ".join(sorted(_BRIEF_KINDS))
            return f"error: unknown kind {kind!r}. available: {available}"
        info = _BRIEF_KINDS[kind]
        template_path = _TEMPLATES_DIR / info["file"]
        if not template_path.exists():
            return f"error: template file not found: {template_path}"
        return template_path.read_text(encoding="utf-8")

    return load_brief_template


def build_write_brief_tool(workspace: Workspace):
    @tool
    def write_brief(path: str, content: str) -> str:
        """Write a completed brief (Markdown) to the ``briefs/`` directory.

        쓰기 가능 디렉토리: ``briefs/`` 전용. 경로는 반드시 ``briefs/`` 로 시작해야
        하며, 파일 확장자는 ``.md`` 여야 합니다. 기존 파일은 덮어씁니다.

        버전 관리: ``briefs/{kind}_v1.md``, ``briefs/{kind}_v2.md`` 처럼 suffix 를
        누적해서 사용합니다.

        서면 저장 후에는 반드시 ``verify_citations(path)`` 와
        ``check_completeness(kind, path)`` 를 호출해 검증하세요.

        Args:
            path: ``briefs/`` 로 시작하는 워크스페이스 상대 경로.
                  예: ``briefs/증거인부서_v1.md``
            content: 완성된 Markdown 서면 전문 (UTF-8).

        Returns:
            ``"wrote {path}"`` on success.
        """
        if not path.startswith("briefs/"):
            return f"error: path must start with 'briefs/', got: {path!r}"
        if not path.endswith(".md"):
            return f"error: brief file must have .md extension, got: {path!r}"
        workspace.write(path, content)
        return f"wrote {path}"

    return write_brief


def build_brief_tools(workspace: Workspace) -> list[Any]:
    """Return all three brief tools as a list."""
    return [
        build_list_brief_templates_tool(),
        build_load_brief_template_tool(),
        build_write_brief_tool(workspace),
    ]
