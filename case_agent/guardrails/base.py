"""Guardrail primitives — Verdict, Decision, Guardrail Protocol.

Mirrors LangChain's ``before_agent`` / ``after_agent`` middleware semantics
(see https://docs.langchain.com/oss/python/langchain/guardrails) but plugs
into the hand-rolled loop in :mod:`case_agent.loop.query` instead of
``create_agent()``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage


class Verdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    rule: str
    reason: str = ""
    replacement: str | None = None

    @classmethod
    def passes(cls, rule: str) -> "Decision":
        return cls(verdict=Verdict.PASS, rule=rule)

    @classmethod
    def blocks(cls, rule: str, replacement: str, reason: str = "") -> "Decision":
        return cls(
            verdict=Verdict.BLOCK,
            rule=rule,
            reason=reason,
            replacement=replacement,
        )


@runtime_checkable
class Guardrail(Protocol):
    name: str

    async def check_before(
        self,
        messages: "Sequence[BaseMessage]",
        system_prompt: str,
    ) -> Decision: ...

    async def check_after(
        self,
        messages: "Sequence[BaseMessage]",
        final_text: str,
    ) -> Decision: ...


__all__ = ["Decision", "Guardrail", "Verdict"]
