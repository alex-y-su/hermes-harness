from __future__ import annotations

import argparse
import json
import os

from harness.tools.user_peer_client import message_peer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cold-start dispatch a message to a registered user peer.")
    parser.add_argument("--peer-id", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--context-id", default=None)
    parser.add_argument("--db-path", default=os.getenv("HARNESS_BRIDGE_DB", ""))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.db_path:
        raise SystemExit("ERROR: --db-path or HARNESS_BRIDGE_DB is required")
    result = message_peer(
        db_path=args.db_path,
        peer_id=args.peer_id,
        message=args.message,
        context_id=args.context_id,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
