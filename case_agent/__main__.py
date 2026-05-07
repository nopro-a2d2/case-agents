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

    args = parser.parse_args()

    if args.cmd == "headless":
        from case_agent.loop.headless import headless_loop
        asyncio.run(headless_loop(args.case, args.root))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
