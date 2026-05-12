"""GuardrailManager — orchestrates a list of Guardrails in parallel.

Used by :mod:`case_agent.loop.query` at two hook points:

* Once before the very first model turn (`before_agent`).
* Once after the model produces an ``end_turn`` final message (`after_agent`).

Both run all guardrails concurrently via :func:`asyncio.gather` and return
the *first* :class:`Decision` with verdict ``BLOCK``. A PASS-only result
returns a synthetic PASS decision.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from case_agent.guardrails.base import Decision, Guardrail, Verdict

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage


class GuardrailManager:
    def __init__(self, guardrails: list[Guardrail]):
        self._guardrails = list(guardrails)

    @property
    def guardrails(self) -> list[Guardrail]:
        return list(self._guardrails)

    async def before_agent(
        self,
        messages: "Sequence[BaseMessage]",
        system_prompt: str,
    ) -> Decision:
        if not self._guardrails:
            return Decision.passes("manager")
        results = await asyncio.gather(
            *(g.check_before(messages, system_prompt) for g in self._guardrails)
        )
        return _first_block(results)

    async def after_agent(
        self,
        messages: "Sequence[BaseMessage]",
        final_text: str,
    ) -> Decision:
        if not self._guardrails:
            return Decision.passes("manager")
        results = await asyncio.gather(
            *(g.check_after(messages, final_text) for g in self._guardrails)
        )
        return _first_block(results)


def _first_block(results: list[Decision]) -> Decision:
    for d in results:
        if d.verdict is Verdict.BLOCK:
            return d
    return Decision.passes("manager")


__all__ = ["GuardrailManager"]
