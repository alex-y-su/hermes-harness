from __future__ import annotations

import argparse
import json

from harness import db
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Acknowledge one operator alert.")
    add_factory_args(parser)
    parser.add_argument("alert_id")
    return parser


def run(args: argparse.Namespace) -> dict:
    _factory, db_path = paths(args)
    with db.session(db_path) as conn:
        row = db.acknowledge_operator_alert(conn, args.alert_id)
        if row is None:
            raise SystemExit(f"unknown alert: {args.alert_id}")
        data = dict(row)
        data["metadata"] = json.loads(data.get("metadata") or "{}")
        return data


def main(argv: list[str] | None = None) -> None:
    print(json.dumps(run(build_parser().parse_args(argv)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
