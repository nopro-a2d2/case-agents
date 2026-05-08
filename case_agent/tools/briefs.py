"""Tools for brief (서면) writing: list templates and write to briefs/ directory."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from ..briefs import list_brief_types, load_template
from ..workspace import Workspace


def build_list_brief_templates_tool():
    @tool
    def list_brief_templates() -> str:
        """List available brief (서면) templates.

        Returns a JSON array of brief type names (e.g. "증거인부서", "준비서면").
        Call this first when asked to write any legal brief.
        """
        return json.dumps(list_brief_types(), ensure_ascii=False)

    return list_brief_templates


def build_get_brief_template_tool():
    @tool
    def get_brief_template(brief_type: str) -> str:
        """Get the Markdown template for a specific brief type.

        Args:
            brief_type: one of the types returned by list_brief_templates
                        (e.g. "증거인부서", "증인심문사항", "피고인심문사항",
                         "변호인의견서", "준비서면")

        Returns:
            The full Markdown template text to be used as the basis for drafting.
        """
        try:
            return load_template(brief_type)
        except KeyError as e:
            return f"오류: {e}"

    return get_brief_template


def build_write_brief_tool(workspace: Workspace):
    @tool
    def write_brief(path: str, content: str) -> str:
        """Write a legal brief (서면) to the briefs/ directory.

        서면은 반드시 briefs/ 경로에 저장해야 합니다 (artifacts/에 저장하지 마세요).

        Args:
            path: briefs/-relative path, e.g. "briefs/증거인부서_v1.md"
            content: full Markdown content of the brief

        Returns:
            "wrote {path}" on success.
        """
        if not path.startswith("briefs/"):
            return f"오류: 서면은 반드시 briefs/ 디렉토리에 저장해야 합니다. 입력된 경로: {path}"
        workspace.write(path, content)
        return f"wrote {path}"

    return write_brief
