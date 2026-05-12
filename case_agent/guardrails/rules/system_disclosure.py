"""Block disclosure of agent implementation / system architecture."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from case_agent.guardrails.base import Decision
from case_agent.guardrails.classifier import classify, decision_from
from case_agent.guardrails.rules.model_identity import _last_human_text

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage


_PROMPT = (
    Path(__file__).parent.parent / "prompts" / "system_disclosure.md"
).read_text(encoding="utf-8")
_REFUSAL = (
    "저는 AiLex AI 입니다. 내부 구현·시스템 구조에 대한 정보는 공개하지 않습니다. "
    "사건 분석·QA·서면 작성과 관련된 요청을 도와드리겠습니다."
)


class SystemDisclosureGuardrail:
    name = "system_disclosure"

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
        final_text: str,
    ) -> Decision:
        text = (final_text or "").strip()
        if not text:
            return Decision.passes(self.name)
        verdict, reason = await classify(self._model, system=_PROMPT, user=text)
        return decision_from(
            verdict, rule=self.name, replacement=_REFUSAL, reason=reason
        )


__all__ = ["SystemDisclosureGuardrail"]
