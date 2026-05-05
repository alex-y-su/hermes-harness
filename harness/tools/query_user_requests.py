from __future__ import annotations

import argparse
import json
from typing import Any

from harness import db
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List user-blocked approval/input/auth requests.")
    add_factory_args(parser)
    parser.add_argument("--status", choices=["open", "supplied", "resuming", "resolved", "denied", "all"], default="open")
    parser.add_argument("--team", default=None)
    parser.add_argument("--assignment-id", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def _decode_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["required_fields"] = json.loads(data.pop("required_fields_json") or "[]")
    data["response"] = json.loads(data.pop("response_json") or "null")
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def run(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    status = None if args.status == "all" else args.status
    with db.session(db_path) as conn:
        requests = [
            _decode_row(row)
            for row in db.list_approval_requests(
                conn,
                status=status,
                team_name=args.team,
                assignment_id=args.assignment_id,
            )
        ]
    return {"status": args.status, "count": len(requests), "requests": requests}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for request in result["requests"]:
        print(
            f"{request['request_id']}: status={request['status']} team={request['team_name']} "
            f"assignment={request['assignment_id']} kind={request['kind']} title={request['title']}"
        )
    if not result["requests"]:
        print(f"no {args.status} user requests")


if __name__ == "__main__":
    main()
