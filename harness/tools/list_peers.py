from __future__ import annotations

import argparse
import json
import os

from harness.bridge.store import BridgeDb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List registered user peers.")
    parser.add_argument("--db-path", default=os.getenv("HARNESS_BRIDGE_DB", ""))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.db_path:
        raise SystemExit("ERROR: --db-path or HARNESS_BRIDGE_DB is required")
    bridge = BridgeDb(args.db_path)
    rows = bridge.list_user_peers()
    peers = [
        {
            "peer_id": row["peer_id"],
            "agent_card_url": row["agent_card_url"],
            "has_token": bool(row["access_token"]),
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]
    print(json.dumps(peers, sort_keys=True))


if __name__ == "__main__":
    main()
