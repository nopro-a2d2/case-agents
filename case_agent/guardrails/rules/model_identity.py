"""Block questions/answers about the underlying LLM model identity."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ..base import Decision
from ..classifier import classify, decision_from

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage


_PROMPT = (Path(__file__).parent.parent / "prompts" / "model_identity.md").read_text(
    encoding="utf-8"
)
_REFUSAL = (
    "저는 AiLex AI 입니다. "
    "사건 분석·QA·서면 작성과 관련된 요청을 도와드리겠습니다."
)


def _last_human_text(messages: "Sequence[BaseMessage]") -> str:
    for m in reversed(messages):
        if getattr(m, "type", None) == "human":
            content = m.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    str(b.get("text", "")) if isinstance(b, dict) else str(b)
                    for b in content
                )
    return ""


class ModelIdentityGuardrail:
    name = "model_identity"

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


__all__ = ["ModelIdentityGuardrail"]
