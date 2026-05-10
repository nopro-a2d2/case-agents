"""Slash *commands* — backend control plane (no model call).

Symmetric to ``case_agent/skills/`` (model plane). Add a new command by
dropping a ``case_agent/commands/<name>.py`` that exports
``build_command() -> tuple[Command, CommandHandler]``.

A command handler runs purely on the server: it can abort the current turn,
reset history/todos, and emit one or more ``StreamEvent``s back to the
client. The model is **not** invoked.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable, Iterable

if TYPE_CHECKING:
    from ..loop.types import StreamEvent


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    argument_hint: str = ""
    when_to_use: str = ""


@dataclass
class CommandContext:
    """Levers a command handler may pull. Caller (headless/ws) constructs
    one per dispatch so handlers don't need to know transport details."""

    abort: Callable[[], Awaitable[None]]
    reset_history: Callable[[], None]
    reset_todos: Callable[[], None]


CommandHandler = Callable[[str, CommandContext], Awaitable[Iterable["StreamEvent"]]]


def discover_commands() -> "dict[str, tuple[Command, CommandHandler]]":
    """Auto-import every non-underscore sibling module and call its
    ``build_command`` factory; aggregate by ``cmd.name``.
    """
    out: dict[str, tuple[Command, CommandHandler]] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f".{info.name}", __package__)
        builder = getattr(mod, "build_command", None)
        if builder is None:
            continue
        cmd, handler = builder()
        out[cmd.name] = (cmd, handler)
    return out


async def try_dispatch(
    prompt: str,
    registry: "dict[str, tuple[Command, CommandHandler]]",
    ctx: CommandContext,
) -> "tuple[bool, list[StreamEvent]]":
    """Run the matching handler for ``/<name> [args]``. Returns
    ``(handled, events_to_emit)``. ``handled=False`` means the prompt was
    not a known command — caller should fall through to skill expansion or
    normal chat."""
    if not prompt.startswith("/"):
        return False, []
    head, _, tail = prompt[1:].partition(" ")
    name = head.strip()
    entry = registry.get(name)
    if entry is None:
        return False, []
    _, handler = entry
    events = list(await handler(tail.strip(), ctx))
    return True, events


__all__ = [
    "Command",
    "CommandContext",
    "CommandHandler",
    "discover_commands",
    "try_dispatch",
]
