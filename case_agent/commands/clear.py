"""``/clear`` — wipe history, todos, and the in-flight turn.

Purely a control-plane action: aborts whatever the model is currently
doing and resets server-side state, then asks the client to mirror via
``Cleared``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from case_agent.commands import Command, CommandContext

if TYPE_CHECKING:
    from case_agent.loop.types import StreamEvent


async def _handle(args: str, ctx: CommandContext) -> "list[StreamEvent]":
    from case_agent.loop.types import Cleared

    await ctx.abort()
    ctx.reset_history()
    ctx.reset_todos()
    return [Cleared()]


def build_command() -> "tuple[Command, object]":
    return (
        Command(
            name="clear",
            description="Start a new session with empty context.",
        ),
        _handle,
    )
