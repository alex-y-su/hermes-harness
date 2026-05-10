from __future__ import annotations

import argparse
import re

from harness import db
from harness.factory import utc_now
from harness.tools.common import add_factory_args, paths


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:80] or "escalation"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a structured escalation into factory/escalations.")
    add_factory_args(parser)
    parser.add_argument("--team", default="fleet")
    parser.add_argument("--kind", default="operator-input-required")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--source", default="harness.escalate")
    return parser


def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    path = factory / "escalations" / f"{utc_now().replace(':', '').replace('-', '')}_{slug(args.team)}_{slug(args.kind)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {args.title}\n\n"
        f"- team: {args.team}\n"
        f"- kind: {args.kind}\n"
        f"- source: {args.source}\n"
        f"- created_at: {utc_now()}\n\n"
        f"{args.body}\n",
        encoding="utf-8",
    )
    with db.session(db_path) as conn:
        db.record_event(
            conn,
            team_name=args.team,
            source=args.source,
            kind="escalation",
            state=args.kind,
            payload_path=str(path),
            metadata={"title": args.title},
        )
    return {"path": str(path)}


def main(argv: list[str] | None = None) -> None:
    result = run(build_parser().parse_args(argv))
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
