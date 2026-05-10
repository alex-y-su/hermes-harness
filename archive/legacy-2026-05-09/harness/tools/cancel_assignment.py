from __future__ import annotations

import argparse
import json

from harness import db
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark one assignment cancel-requested.")
    add_factory_args(parser)
    parser.add_argument("assignment_id")
    parser.add_argument("--reason", default="operator requested cancellation")
    return parser


def run(args: argparse.Namespace) -> dict:
    _factory, db_path = paths(args)
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (args.assignment_id,)).fetchone()
        if row is None:
            raise SystemExit(f"unknown assignment: {args.assignment_id}")
        if row["status"] in {"completed", "failed", "canceled", "archived"}:
            raise SystemExit(f"assignment is already terminal: {row['status']}")
        conn.execute(
            """
            UPDATE team_assignments
            SET status = 'cancel-requested',
                status_reason = ?,
                lease_owner = NULL,
                lease_expires_at = NULL
            WHERE assignment_id = ?
            """,
            (args.reason, args.assignment_id),
        )
        db.release_lease(conn, resource_type="assignment", resource_id=args.assignment_id)
        db.record_event(
            conn,
            team_name=row["team_name"],
            assignment_id=args.assignment_id,
            task_id=row["a2a_task_id"],
            source="harness.cancel_assignment",
            kind="cancel-requested",
            state="cancel-requested",
            metadata={"reason": args.reason},
        )
        updated = conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (args.assignment_id,)).fetchone()
        return dict(updated)


def main(argv: list[str] | None = None) -> None:
    print(json.dumps(run(build_parser().parse_args(argv)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
