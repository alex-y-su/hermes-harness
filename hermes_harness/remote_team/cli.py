from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from hermes_harness.remote_team import PROTOCOL_VERSION
from hermes_harness.remote_team.poller import poll_once
from hermes_harness.remote_team.protocol import ProtocolError, error_response, read_request, write_response
from hermes_harness.remote_team.receiver import health, receive
from hermes_harness.remote_team.transports import TransportError, call_team


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-harness-remote-team")
    sub = parser.add_subparsers(dest="command", required=True)

    call = sub.add_parser("call", help="Call a registered remote team.")
    call.add_argument("--team", required=True, help="Remote team name.")
    call.add_argument("--operation", required=True, choices=["submit_or_get", "status", "health"])
    call.add_argument("--registry", type=Path, default=None, help="Remote-team registry JSON.")
    call.add_argument("--timeout", type=int, default=60, help="Transport timeout in seconds.")
    call.add_argument("--json", action="store_true", help="Read/write JSON.")

    recv = sub.add_parser("receive", help="Receive one remote-team protocol request on stdin.")
    recv.add_argument("--json", action="store_true", help="Read/write JSON.")

    health_cmd = sub.add_parser("health", help="Report local remote-team health.")
    health_cmd.add_argument("--json", action="store_true", help="Emit JSON.")

    poll = sub.add_parser("poll", help="Poll running remote-team Kanban cards.")
    poll.add_argument("--registry", type=Path, default=None, help="Remote-team registry JSON.")
    poll.add_argument("--board", default=None, help="Kanban board to poll. Defaults to current board.")
    poll.add_argument("--all-boards", action="store_true", help="Poll all non-archived Kanban boards.")
    poll.add_argument("--limit", type=int, default=50, help="Maximum due cards to poll in one pass.")
    poll.add_argument("--sleep-seconds", type=int, default=60, help="Loop sleep interval.")
    poll.add_argument("--loop", action="store_true", help="Keep polling until interrupted.")
    poll.add_argument("--dry-run", action="store_true", help="Report due cards without calling remote teams.")
    poll.add_argument("--json", action="store_true", help="Emit JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "call":
            request = read_request() if args.json else {}
            response = call_team(
                registry_path=args.registry or _default_registry(),
                team=args.team,
                operation=args.operation,
                request=request,
                timeout=args.timeout,
            )
            write_response(response)
            return 0 if response.get("ok") else 1
        if args.command == "receive":
            request = read_request()
            write_response(receive(request))
            return 0
        if args.command == "health":
            write_response(health())
            return 0
        if args.command == "poll":
            while True:
                response = poll_once(
                    registry_path=args.registry or None,
                    board=args.board,
                    all_boards=args.all_boards,
                    limit=args.limit,
                    dry_run=args.dry_run,
                )
                write_response(response)
                if not args.loop:
                    return 0 if response.get("ok") else 1
                time.sleep(max(1, int(args.sleep_seconds)))
    except (ProtocolError, TransportError, RuntimeError) as exc:
        write_response(error_response(str(exc), code=exc.__class__.__name__))
        return 1
    raise SystemExit(f"unknown command: {args.command}")


def _default_registry() -> Path:
    configured = os.environ.get("HERMES_REMOTE_TEAMS_CONFIG")
    if configured:
        return Path(configured)
    return Path(os.environ.get("HERMES_HOME", ".")) / "remote_teams.json"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
