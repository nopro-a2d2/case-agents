"""LLM-backed binary classifier used by the rule modules.

Calls the light guard model (default ``gemini-3.1-flash-lite-preview``) with
a tightly-scoped prompt and parses the response as JSON
``{"verdict": "pass"|"block", "reason": "..."}``.

**Fail-open**: any classifier error (timeout, parse failure, model exception)
yields :data:`Verdict.PASS`. Availability over strict enforcement — a downed
guard must never lock the agent.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from .base import Decision, Verdict

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


logger = logging.getLogger(__name__)


_JSON_OBJ_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _coerce_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("text") or block.get("content")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _parse_verdict(raw: str) -> tuple[Verdict, str]:
    """Best-effort JSON extraction. Returns (verdict, reason)."""
    m = _JSON_OBJ_RE.search(raw)
    payload = m.group(0) if m else raw
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        norm = raw.strip().lower()
        if norm.startswith("block"):
            return Verdict.BLOCK, ""
        return Verdict.PASS, ""
    v = str(data.get("verdict", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()
    return (Verdict.BLOCK if v == "block" else Verdict.PASS), reason


async def classify(
    model: "BaseChatModel",
    *,
    system: str,
    user: str,
) -> tuple[Verdict, str]:
    """Run a single classification turn. Returns (verdict, reason).

    On any exception, logs at WARNING level and returns ``(Verdict.PASS, "")``.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        result = await model.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("guardrail classifier failed: %s: %s", type(e).__name__, e)
        return Verdict.PASS, ""

    text = _coerce_text(getattr(result, "content", ""))
    return _parse_verdict(text)


def decision_from(
    verdict: Verdict,
    *,
    rule: str,
    replacement: str,
    reason: str = "",
) -> Decision:
    if verdict is Verdict.BLOCK:
        return Decision.blocks(rule=rule, replacement=replacement, reason=reason)
    return Decision.passes(rule)


__all__ = ["classify", "decision_from"]
