from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from harness_remote.a2a_server import RemoteRuntimeConfig, RemoteRuntimeServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Hermes Harness remote supervisor runtime.")
    sub = parser.add_subparsers(dest="command")
    start = sub.add_parser("start", help="Start the remote A2A supervisor")
    start.add_argument("--team-name", default=os.getenv("HARNESS_REMOTE_TEAM_NAME", "remote"))
    start.add_argument("--template", choices=["single-agent", "multi-agent"], default=os.getenv("HARNESS_REMOTE_TEMPLATE", "single-agent"))
    start.add_argument("--boss-push-url", default=os.getenv("BOSS_PUSH_URL") or os.getenv("HARNESS_REMOTE_PUSH_URL"))
    start.add_argument("--push-token", default=os.getenv("HARNESS_REMOTE_PUSH_TOKEN"))
    start.add_argument("--bridge-secret", default=os.getenv("HARNESS_REMOTE_BRIDGE_SECRET"))
    start.add_argument("--host", default=os.getenv("HARNESS_REMOTE_HOST", "127.0.0.1"))
    start.add_argument("--a2a-port", "--port", type=int, default=int(os.getenv("HARNESS_REMOTE_A2A_PORT", "8000")))
    start.add_argument("--ready-file", default=os.getenv("HARNESS_REMOTE_READY_FILE"))
    start.add_argument("--artifact-text", default=os.getenv("HARNESS_REMOTE_ARTIFACT_TEXT", "Remote runtime completed the assignment."))
    start.add_argument("--runner", choices=["mock", "command", "codex"], default=os.getenv("HARNESS_REMOTE_RUNNER", "mock"))
    start.add_argument("--runner-command", default=os.getenv("HARNESS_REMOTE_RUNNER_COMMAND"))
    start.add_argument("--runner-timeout-seconds", type=int, default=int(os.getenv("HARNESS_REMOTE_RUNNER_TIMEOUT_SECONDS", "900")))
    start.add_argument("--workspace", default=os.getenv("HARNESS_REMOTE_WORKSPACE", "/home/user/workspace"))
    return parser


def run_start(args: argparse.Namespace) -> None:
    missing = [
        name
        for name, value in {
            "BOSS_PUSH_URL/--boss-push-url": args.boss_push_url,
            "HARNESS_REMOTE_PUSH_TOKEN/--push-token": args.push_token,
            "HARNESS_REMOTE_BRIDGE_SECRET/--bridge-secret": args.bridge_secret,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("missing required remote runtime settings: " + ", ".join(missing))
    runtime = RemoteRuntimeServer(
        RemoteRuntimeConfig(
            team_name=args.team_name,
            push_url=args.boss_push_url,
            push_token=args.push_token,
            bridge_secret=args.bridge_secret,
            artifact_text=args.artifact_text,
            host=args.host,
            port=args.a2a_port,
            runner_mode=args.runner,
            runner_command=args.runner_command,
            runner_timeout_seconds=args.runner_timeout_seconds,
            workspace=args.workspace,
        )
    )
    if args.ready_file:
        ready_path = Path(args.ready_file)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_text(json.dumps({"agent_card_url": runtime.agent_card_url}, indent=2) + "\n", encoding="utf-8")
    runtime.serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {None, "start"}:
        run_start(args)
        return
    parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
