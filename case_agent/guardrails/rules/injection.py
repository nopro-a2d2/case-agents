"""Detect prompt-injection / jailbreak attempts in user input."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ..base import Decision
from ..classifier import classify, decision_from
from .model_identity import _last_human_text

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage


_PROMPT = (Path(__file__).parent.parent / "prompts" / "injection.md").read_text(
    encoding="utf-8"
)
_REFUSAL = (
    "저는 AiLex AI 입니다. 해당 요청은 답변드릴 수 없습니다. "
    "사건과 관련된 질문을 다시 입력해 주세요."
)


class PromptInjectionGuardrail:
    name = "prompt_injection"

    def __init__(self, model: "BaseChatModel"):
        self._model = model

    async def check_before(
        self,
        messages: "Sequence[BaseMessage]",
        system_prompt: str,  # noqa: ARG002
    ) -> Decision:
        user = _last_human_text(messages).strip()
        if not user:
            return Decision.passes(self.name)
        verdict, reason = await classify(self._model, system=_PROMPT, user=user)
        return decision_from(
            verdict, rule=self.name, replacement=_REFUSAL, reason=reason
        )

    async def check_after(
        self,
        messages: "Sequence[BaseMessage]",  # noqa: ARG002
        final_text: str,  # noqa: ARG002
    ) -> Decision:
        # Injection is an input-side concern; final output is governed by the
        # other two guardrails.
        return Decision.passes(self.name)


__all__ = ["PromptInjectionGuardrail"]
