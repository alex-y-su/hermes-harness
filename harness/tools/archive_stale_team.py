from __future__ import annotations

import argparse
import json

from harness import db
from harness.factory import archive_team, team_path, utc_now
from harness.tools.common import add_factory_args, paths


ACTIVE_STATUSES = {"queued", "pending", "dispatched", "working", "resuming", "retrying", "stale", "input-required", "auth-required"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archive a stale team when no active work remains.")
    add_factory_args(parser)
    parser.add_argument("team")
    parser.add_argument("--force", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict:
    factory, db_path = paths(args)
    team_dir = team_path(factory, args.team)
    if not team_dir.exists():
        raise SystemExit(f"team does not exist: {args.team}")
    with db.session(db_path) as conn:
        active = list(
            conn.execute(
                f"""
                SELECT assignment_id, status
                FROM team_assignments
                WHERE team_name = ?
                  AND status IN ({",".join("?" for _ in ACTIVE_STATUSES)})
                """,
                (args.team, *sorted(ACTIVE_STATUSES)),
            )
        )
        if active and not args.force:
            raise SystemExit(f"team has active work; use --force to archive anyway: {[row['assignment_id'] for row in active]}")
        halt_path = team_dir / "HALT.flag"
        halt_path.write_text(f"archive requested at {utc_now()} by harness.archive_stale_team\n", encoding="utf-8")
        archive_path = archive_team(factory, args.team)
        db.mark_handle_archived(conn, args.team)
        db.record_event(
            conn,
            team_name=args.team,
            source="harness.archive_stale_team",
            kind="archived",
            state="archived",
            payload_path=str(archive_path),
            metadata={"force": args.force, "active_assignments": [dict(row) for row in active]},
        )
    return {"team": args.team, "archive": str(archive_path), "forced": args.force}


def main(argv: list[str] | None = None) -> None:
    print(json.dumps(run(build_parser().parse_args(argv)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
