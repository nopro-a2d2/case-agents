"""Entry point for ``python -m case_agent``.

Usage:
    python -m case_agent headless --case <id> --root <path>
"""

from __future__ import annotations

import argparse
import asyncio


def main() -> None:
    parser = argparse.ArgumentParser(prog="case_agent")
    sub = parser.add_subparsers(dest="cmd")

    h = sub.add_parser("headless", help="Stdio NDJSON bridge for the TypeScript TUI")
    h.add_argument("--case", required=True, help="Case ID")
    h.add_argument("--root", required=True, help="Workspace root path")

    s = sub.add_parser("serve", help="WebSocket server for the web frontend")
    s.add_argument("--case", required=True, help="Case ID")
    s.add_argument("--root", required=True, help="Workspace root path")
    s.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host. Use 0.0.0.0 for LAN/IP access. Default: 127.0.0.1",
    )
    s.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    s.add_argument(
        "--static-dir",
        default=None,
        help=(
            "Directory containing the built web frontend (web/dist). "
            "If omitted, auto-detects <cwd>/web/dist. Pass an empty string "
            "to disable static serving (dev with vite proxy)."
        ),
    )

    args = parser.parse_args()

    if args.cmd == "headless":
        from case_agent.loop.headless import headless_loop
        asyncio.run(headless_loop(args.case, args.root))
    elif args.cmd == "serve":
        try:
            import uvicorn
        except ImportError as e:
            raise SystemExit(
                "uvicorn is not installed. Install web extras with: uv sync --extra web"
            ) from e
        import logging
        from pathlib import Path

        from case_agent.loop.ws_server import create_app

        logging.getLogger("case_agent.ws").setLevel(logging.INFO)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )

        static_dir: Path | None
        if args.static_dir == "":
            static_dir = None
        elif args.static_dir is None:
            auto = Path.cwd() / "web" / "dist"
            static_dir = auto if auto.exists() else None
        else:
            static_dir = Path(args.static_dir)

        app = create_app(args.case, args.root, static_dir=static_dir)
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
