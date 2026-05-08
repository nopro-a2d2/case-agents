"""Thin WebSocket adapter — same NDJSON event schema as headless stdio.

Protocol (per WS connection):
  client → server text frames (JSON):
      {"prompt": "...", "force_strategy": false}
      {"type": "abort"}
  server → client text frames (JSON): same shape as headless._serialize output.

This module adds zero new business logic; it forwards events from
`stream_query` through `headless._serialize`. The `headless` subcommand and
`scripts/run_benchmark.py` are unaffected.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import BaseMessage, HumanMessage

from ..observability import flush as _obs_flush
from .headless import _serialize
from .runner import stream_query
from .types import Done

logger = logging.getLogger("case_agent.ws")


def create_app(case: str, root: str, static_dir: Path | None = None) -> FastAPI:
    """Build a FastAPI app bound to one (case, root) pair.

    Each WS connection gets its own component set and history, so concurrent
    browser tabs don't share LangChain memory.

    When ``static_dir`` points at an existing directory containing
    ``index.html``, the app also serves the built web frontend so the whole
    thing runs on a single port (useful for IP/LAN deployment).
    """
    app = FastAPI(title="case-agent web bridge")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "case": case, "root": root}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()

        from ..agent import build_case_agent_components
        from ..workspace import LocalFS

        workspace = LocalFS(case_id=case, root=root)
        components = build_case_agent_components(workspace)
        history: list[BaseMessage] = []

        # One Langfuse session per WS connection — every turn in this
        # browser tab rolls up under it.
        chat_session_id = f"ws-{uuid.uuid4().hex[:12]}"

        abort_event = asyncio.Event()
        run_task: asyncio.Task[None] | None = None

        async def run_turn(prompt: str, force_strategy: bool) -> None:
            nonlocal history
            history.append(HumanMessage(content=prompt))
            logger.info(
                "ws turn start prompt=%r force_strategy=%s history_len=%d",
                prompt[:80], force_strategy, len(history),
            )
            event_count = 0
            try:
                async for ev in stream_query(
                    prompt,
                    components,
                    messages=history,
                    abort=abort_event,
                    force_strategy=force_strategy,
                    session_id=chat_session_id,
                ):
                    event_count += 1
                    payload = _serialize(ev)
                    if event_count <= 3 or payload.get("type") in ("tool_start", "tool_end", "done", "error"):
                        logger.info("ws event #%d type=%s", event_count, payload.get("type"))
                    await ws.send_text(
                        json.dumps(payload, ensure_ascii=False, default=str)
                    )
                    if isinstance(ev, Done):
                        if ev.terminal.messages:
                            history = list(ev.terminal.messages)
                        # Long-lived process: flush per turn.
                        _obs_flush()
                logger.info("ws turn finished events=%d", event_count)
            except Exception as e:  # noqa: BLE001 — surface to client as JSON
                logger.exception("ws turn failed after %d events", event_count)
                try:
                    await ws.send_text(
                        json.dumps({"type": "error", "error": str(e)})
                    )
                except Exception:  # noqa: BLE001
                    pass

        logger.info(
            "ws connection open case=%s root=%s langfuse_session=%s",
            case, root, chat_session_id,
        )
        try:
            while True:
                raw = await ws.receive_text()
                logger.info("ws frame received bytes=%d", len(raw))
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as e:
                    await ws.send_text(
                        json.dumps({"type": "error", "error": f"invalid json: {e}"})
                    )
                    continue

                # Abort frame
                if payload.get("type") == "abort":
                    abort_event.set()
                    continue

                # Prompt frame
                prompt = payload.get("prompt") or ""
                if not prompt:
                    continue
                force_strategy = bool(payload.get("force_strategy", False))

                # Drop if a previous turn is still running.
                if run_task and not run_task.done():
                    await ws.send_text(
                        json.dumps({"type": "error", "error": "turn in progress"})
                    )
                    continue

                abort_event = asyncio.Event()
                run_task = asyncio.create_task(run_turn(prompt, force_strategy))
        except WebSocketDisconnect:
            abort_event.set()
            if run_task:
                run_task.cancel()
        except Exception:  # noqa: BLE001
            logger.exception("ws connection error")
            abort_event.set()
            if run_task:
                run_task.cancel()

    # Optional: serve the built web frontend from the same port.
    # Routes defined above (/healthz, /ws) take precedence over the SPA
    # catch-all because FastAPI matches in registration order.
    if static_dir is not None and static_dir.exists() and (static_dir / "index.html").exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="assets",
            )

        index_path = static_dir / "index.html"

        @app.get("/")
        async def spa_root() -> FileResponse:
            return FileResponse(index_path)

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            # Serve files at the root of dist (favicon, manifest, etc.)
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            # Otherwise fall back to index.html for client-side routing.
            if index_path.exists():
                return FileResponse(index_path)
            raise HTTPException(status_code=404)

    return app


__all__ = ["create_app"]
