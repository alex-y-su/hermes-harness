from __future__ import annotations

import argparse
import uuid

from harness import db
from harness.factory import team_path, utc_now, write_json
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write an assignment envelope into a remote team's inbox.")
    add_factory_args(parser)
    parser.add_argument("team")
    parser.add_argument("--assignment-id", default=None)
    parser.add_argument("--order-id", default=None)
    parser.add_argument("--title", default="Remote assignment")
    parser.add_argument("--body", default=None)
    parser.add_argument("--file", default=None, help="Markdown body file")
    return parser


def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    assignment_id = args.assignment_id or f"asn-{uuid.uuid4().hex[:12]}"
    team_dir = team_path(factory, args.team)
    if not team_dir.exists():
        raise SystemExit(f"team does not exist: {args.team}")
    body = args.body
    if args.file:
        body = open(args.file, encoding="utf-8").read()
    body = body or ""
    inbox_path = team_dir / "inbox" / f"{assignment_id}.md"
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_path.write_text(
        f"# {args.title}\n\n"
        f"- assignment_id: {assignment_id}\n"
        f"- order_id: {args.order_id or ''}\n"
        f"- team: {args.team}\n"
        f"- created_at: {utc_now()}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    write_json(
        inbox_path.with_suffix(".queued.json"),
        {"assignment_id": assignment_id, "team": args.team, "state": "queued", "created_at": utc_now()},
    )
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id=assignment_id,
            team_name=args.team,
            order_id=args.order_id,
            status="queued",
            inbox_path=str(inbox_path),
        )
        db.record_event(
            conn,
            team_name=args.team,
            assignment_id=assignment_id,
            source="hr.dispatch_team",
            kind="queued",
            state="queued",
            payload_path=str(inbox_path),
        )
    return {"assignment_id": assignment_id, "path": str(inbox_path)}


def main(argv: list[str] | None = None) -> None:
    result = run(build_parser().parse_args(argv))
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
