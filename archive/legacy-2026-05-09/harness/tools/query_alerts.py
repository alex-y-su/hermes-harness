from __future__ import annotations

import argparse
import json
from typing import Any

from harness import db
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List operator alerts.")
    add_factory_args(parser)
    parser.add_argument("--status", default="open", help="open, acknowledged, or all")
    parser.add_argument("--severity", default=None)
    parser.add_argument("--kind", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def _decode(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def run(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    with db.session(db_path) as conn:
        alerts = [
            _decode(row)
            for row in db.list_operator_alerts(
                conn,
                status=args.status,
                severity=args.severity,
                kind=args.kind,
            )
        ]
    return {"count": len(alerts), "alerts": alerts}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for alert in result["alerts"]:
        print(f"{alert['alert_id']} {alert['severity']} {alert['kind']}: {alert['title']}")
    if not result["alerts"]:
        print("no alerts")


if __name__ == "__main__":
    main()
