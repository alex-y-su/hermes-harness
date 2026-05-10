from __future__ import annotations

import argparse
import asyncio

from harness import db
from harness.factory import archive_team, team_path, utc_now
from harness.substrate.factory import build_driver
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write HALT, cancel active assignments, and archive a remote team.")
    add_factory_args(parser)
    parser.add_argument("team")
    parser.add_argument("--dry-run", action="store_true", help="Skip substrate side effects")
    parser.add_argument("--no-archive", action="store_true", help="Leave the local team folder in place")
    return parser


async def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    team_dir = team_path(factory, args.team)
    if not team_dir.exists():
        raise SystemExit(f"team does not exist: {args.team}")
    halt_path = team_dir / "HALT.flag"
    halt_path.write_text(f"halt requested at {utc_now()} by hr.sunset_team\n", encoding="utf-8")

    archive_path = ""
    with db.session(db_path) as conn:
        handle = db.load_substrate_handle(conn, args.team)
        active = db.active_assignments(conn, args.team)
        for row in active:
            db.upsert_assignment(
                conn,
                assignment_id=row["assignment_id"],
                team_name=args.team,
                order_id=row["order_id"],
                a2a_task_id=row["a2a_task_id"],
                status="cancel-requested",
                inbox_path=row["inbox_path"],
                in_flight_path=row["in_flight_path"],
                completed_path=row["completed_path"],
            )
        db.record_event(
            conn,
            team_name=args.team,
            source="hr.sunset_team",
            kind="cancel-requested",
            state="cancel-requested",
            payload_path=str(halt_path),
            metadata={"active_assignments": len(active), "dry_run": args.dry_run},
        )

    if handle and not args.dry_run:
        driver = build_driver(handle.substrate, dry_run=False)
        await driver.cancel(handle)
        await driver.archive(handle, factory / "archive" / f"substrate_{args.team}")

    if not args.no_archive:
        destination = archive_team(factory, args.team)
        archive_path = str(destination)
        with db.session(db_path) as conn:
            db.mark_handle_archived(conn, args.team)
            db.record_event(
                conn,
                team_name=args.team,
                source="hr.sunset_team",
                kind="archived",
                state="archived",
                payload_path=archive_path,
                metadata={"dry_run": args.dry_run},
            )

    return {"team": args.team, "halt": str(halt_path), "archive": archive_path or "not archived"}


def main(argv: list[str] | None = None) -> None:
    result = asyncio.run(run(build_parser().parse_args(argv)))
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
