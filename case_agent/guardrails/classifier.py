"""LLM-backed binary classifier used by the rule modules.

Calls the light guard model (default ``gemini-3.1-flash-lite-preview``) with
a tightly-scoped prompt and uses LangChain ``with_structured_output(...)`` to
force a :class:`GuardrailVerdict` Pydantic response. The model API enforces
the schema (Gemini native ``responseSchema`` / function-calling), eliminating
the prose/code-fence brittleness of regex-based JSON extraction.

**Retry**: up to 3 retries (4 attempts total) on any exception
(``ValidationError``, transient API errors, etc.).

**Fail-open**: after retries are exhausted, any classifier failure yields
:data:`Verdict.PASS`. Availability over strict enforcement — a downed guard
must never lock the agent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from case_agent.guardrails.base import Decision, Verdict

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 4  # 1 initial + 3 retries


class GuardrailVerdict(BaseModel):
    verdict: Literal["pass", "block"]
    reason: str = Field(default="")


async def classify(
    model: "BaseChatModel",
    *,
    system: str,
    user: str,
) -> tuple[Verdict, str]:
    """Run a single classification turn. Returns (verdict, reason).

    Retries up to 3 times on any exception. On exhaustion, logs at WARNING
    level and returns ``(Verdict.PASS, "")``.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    bound = model.with_structured_output(GuardrailVerdict)
    messages = [SystemMessage(content=system), HumanMessage(content=user)]

    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result: GuardrailVerdict = await bound.ainvoke(messages)
        except Exception as e:  # noqa: BLE001 — fail-open after retries
            last_exc = e
            logger.debug(
                "guardrail classifier attempt %d/%d failed: %s: %s",
                attempt,
                MAX_ATTEMPTS,
                type(e).__name__,
                e,
            )
            continue

        verdict = Verdict.BLOCK if result.verdict == "block" else Verdict.PASS
        return verdict, result.reason

    logger.warning(
        "guardrail classifier failed after %d attempts: %s: %s",
        MAX_ATTEMPTS,
        type(last_exc).__name__ if last_exc else "Unknown",
        last_exc,
    )
    return Verdict.PASS, ""


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


__all__ = ["GuardrailVerdict", "classify", "decision_from"]
