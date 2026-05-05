"""Textual chat TUI for case-agent."""

from __future__ import annotations


def launch_chat(*args, **kwargs):  # pragma: no cover - thin re-export
    """Defer the heavy ``textual`` import until first use."""
    from .app import launch_chat as _impl

    return _impl(*args, **kwargs)


__all__ = ["launch_chat"]
