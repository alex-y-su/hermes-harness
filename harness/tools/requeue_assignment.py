from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness import db
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Requeue a retrying or stale assignment.")
    add_factory_args(parser)
    parser.add_argument("assignment_id")
    parser.add_argument("--force", action="store_true", help="Allow requeue when an A2A task id already exists")
    return parser


def run(args: argparse.Namespace) -> dict:
    _factory, db_path = paths(args)
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (args.assignment_id,)).fetchone()
        if row is None:
            raise SystemExit(f"unknown assignment: {args.assignment_id}")
        if row["a2a_task_id"] and not args.force:
            raise SystemExit("assignment has an A2A task id; use --force after confirming duplicate dispatch is acceptable")
        inbox_path = Path(row["inbox_path"])
        in_flight_path = Path(row["in_flight_path"]) if row["in_flight_path"] else None
        if not inbox_path.exists() and in_flight_path and in_flight_path.exists():
            inbox_path.parent.mkdir(parents=True, exist_ok=True)
            in_flight_path.replace(inbox_path)
        conn.execute(
            """
            UPDATE team_assignments
            SET status = 'queued',
                status_reason = 'operator requeued',
                a2a_task_id = CASE WHEN ? THEN NULL ELSE a2a_task_id END,
                next_retry_at = NULL,
                lease_owner = NULL,
                lease_expires_at = NULL,
                terminal_at = NULL
            WHERE assignment_id = ?
            """,
            (1 if args.force else 0, args.assignment_id),
        )
        db.release_lease(conn, resource_type="assignment", resource_id=args.assignment_id)
        db.record_event(
            conn,
            team_name=row["team_name"],
            assignment_id=args.assignment_id,
            task_id=row["a2a_task_id"],
            source="harness.requeue_assignment",
            kind="requeued",
            state="queued",
            metadata={"force": args.force},
        )
        updated = conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (args.assignment_id,)).fetchone()
        return dict(updated)


def main(argv: list[str] | None = None) -> None:
    print(json.dumps(run(build_parser().parse_args(argv)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
