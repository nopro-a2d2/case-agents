"""Before/after agent guardrails for case-agents.

Public API:

* :class:`GuardrailManager` — orchestrates rules at the loop's hook points.
* :func:`build_default_guardrails` — wires the three rules required by the
  product (model identity, prompt injection, system disclosure) onto the
  light guard model (default ``gemini-3.1-flash-lite-preview``).
* :class:`Verdict`, :class:`Decision`, :class:`Guardrail` — primitives.

Concept maps to LangChain's ``before_agent`` / ``after_agent`` middleware
(https://docs.langchain.com/oss/python/langchain/guardrails) but plugs into
the project's hand-rolled loop, not ``create_agent()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from case_agent.guardrails.base import Decision, Guardrail, Verdict
from case_agent.guardrails.manager import GuardrailManager
from case_agent.guardrails.rules import (
    ModelIdentityGuardrail,
    PromptInjectionGuardrail,
    SystemDisclosureGuardrail,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


DEFAULT_GUARD_MODEL = "gemini-3.1-flash-lite-preview"


def build_default_guardrails(
    model: "BaseChatModel | None" = None,
) -> GuardrailManager:
    """Return a manager with the three product-required rules wired up.

    ``model`` is the LLM used to classify inputs/outputs. When ``None``, a
    fresh ``gemini-3.1-flash-lite-preview`` Vertex client is built via
    :func:`case_agent.model.build_light` with ``temperature=0`` and a tight
    ``max_output_tokens`` budget.
    """
    if model is None:
        from case_agent.model import build_light

        model = build_light(
            model=DEFAULT_GUARD_MODEL,
            temperature=0.0,
            max_output_tokens=128,
        )
    return GuardrailManager(
        [
            PromptInjectionGuardrail(model),
            ModelIdentityGuardrail(model),
            SystemDisclosureGuardrail(model),
        ]
    )


__all__ = [
    "DEFAULT_GUARD_MODEL",
    "Decision",
    "Guardrail",
    "GuardrailManager",
    "ModelIdentityGuardrail",
    "PromptInjectionGuardrail",
    "SystemDisclosureGuardrail",
    "Verdict",
    "build_default_guardrails",
]
