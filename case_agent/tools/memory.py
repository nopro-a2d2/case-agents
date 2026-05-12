"""LangChain tool wrappers around :mod:`case_agent.memory.memdir`.

Three tools, mirroring Claude Code's two-step memory protocol:

* :func:`build_read_memory_index_tool` — returns ``MEMORY.md`` so the model
  can scan one-line entries before deciding what to recall.
* :func:`build_read_memory_tool`       — fetches one entry by name.
* :func:`build_write_memory_tool`      — saves/updates an entry and refreshes
  the index.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.tools import tool

from case_agent.memory.memdir import MemoryEntry
from case_agent.memory.memdir import read_memory as _read_memory
from case_agent.memory.memdir import read_memory_index as _read_memory_index
from case_agent.memory.memdir import write_memory as _write_memory
from case_agent.workspace import Workspace


def build_read_memory_index_tool(workspace: Workspace):
    @tool
    def read_memory_index() -> str:
        """Return MEMORY.md — one-line summaries of every stored memory.

        Use BEFORE deciding whether to recall a specific memory. The index
        lists each memory's name, description, and type (user/feedback/project).
        Returns the raw markdown index, or an empty string if no memories
        have been written yet.

        When to call:
          - Start of a non-trivial task: scan to see if any user/feedback/project
            entry is relevant.
          - Before asking the user something they may have answered before.

        When NOT to call:
          - Single-fact lookups answered by smart_search alone.
          - Inside loops; one call per task is enough.
        """
        return _read_memory_index(workspace)

    return read_memory_index


def build_read_memory_tool(workspace: Workspace):
    @tool
    def read_memory(name: str) -> str:
        """Read one memory file by its name (without .md suffix is fine).

        Names appear in MEMORY.md (e.g. "lawyer_profile", "spark_case_status").
        Returns JSON with ``name``, ``description``, ``type``, ``body``.
        On not-found, returns ``{"error": "..."}``.

        Use AFTER scanning MEMORY.md and identifying a relevant entry —
        do not guess names.
        """
        try:
            entry = _read_memory(workspace, name)
        except FileNotFoundError:
            return json.dumps({"error": f"no memory named {name!r}"}, ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        return json.dumps(entry.to_dict(), ensure_ascii=False, indent=2)

    return read_memory


def build_write_memory_tool(workspace: Workspace):
    @tool
    def write_memory(
        name: str,
        type: Literal["user", "feedback", "project"],
        description: str,
        body: str,
    ) -> str:
        """Save or update a memory entry and refresh MEMORY.md.

        Types:
          - ``user``     변호사 프로필 (전문 분야, 서면 스타일, 인용 형식 선호 등)
          - ``feedback`` 변호사가 준 교정·합의 사항 (반복 요구하지 않도록 보존)
          - ``project``  사건 상태 추적 (사건번호·재판부·진행 단계·다음 기일·미해결 쟁점)

        When to save:
          - 변호사가 작업 중 명시적으로 교정·합의·선호를 표현했을 때 (feedback)
          - 사건 진행 상태가 바뀌거나 새 정보가 확인됐을 때 (project)
          - 변호사의 서면 스타일·표현 선호를 학습했을 때 (user)
          - 사용자가 "기억해 둬"라고 명시 요청한 경우

        When NOT to save:
          - 워크스페이스(wiki/json/sources) 자체에서 도출 가능한 사실
          - 일회성 작업의 임시 상태 (Todo로 처리)
          - 의뢰인 비밀에 해당하는 사실 — 사건 디렉토리 외부에 노출되지 않도록
            요약·일반화하거나 저장하지 말 것

        Args:
            name: 짧은 식별자 (예: "lawyer_profile", "spark_case"). 슬래시 금지.
                  ``.md`` 접미사는 자동 처리.
            type: "user" | "feedback" | "project"
            description: MEMORY.md 인덱스에 들어갈 한 줄 요약 (≤150자 권장)
            body: 본문 markdown. feedback/project 는 "사실/규칙 → 왜 → 어떻게
                  적용" 3줄 구조를 권장.

        Returns JSON ``{"ok": true, "path": "memory/<name>.md"}`` on success,
        or ``{"error": "..."}`` on validation failure.
        """
        try:
            entry = MemoryEntry(name=name, description=description, type=type, body=body)
            path = _write_memory(workspace, entry)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        return json.dumps({"ok": True, "path": path}, ensure_ascii=False)

    return write_memory


def build_memory_tools(workspace: Workspace) -> list[Any]:
    """Convenience: every memory tool, ready to register on the agent."""
    return [
        build_read_memory_index_tool(workspace),
        build_read_memory_tool(workspace),
        build_write_memory_tool(workspace),
    ]
