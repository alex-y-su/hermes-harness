from __future__ import annotations

import argparse
import json
import os

from harness.tools.user_peer_client import notify_user_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Push a notification to a user_context's push_url.")
    parser.add_argument("--context-id", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--db-path", default=os.getenv("HARNESS_BRIDGE_DB", ""))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.db_path:
        raise SystemExit("ERROR: --db-path or HARNESS_BRIDGE_DB is required")
    result = notify_user_context(db_path=args.db_path, context_id=args.context_id, message=args.message)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
