from __future__ import annotations

import argparse
import asyncio
import shutil

from harness import db
from harness.factory import team_path, utc_now
from harness.substrate.factory import build_driver
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forensically sync/copy a team's internal folder on demand.")
    add_factory_args(parser)
    parser.add_argument("team")
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    team_dir = team_path(factory, args.team)
    if not team_dir.exists():
        raise SystemExit(f"team does not exist: {args.team}")
    destination = factory / "inspections" / f"{args.team}_{utc_now().replace(':', '').replace('-', '')}"
    destination.mkdir(parents=True, exist_ok=True)

    with db.session(db_path) as conn:
        handle = db.load_substrate_handle(conn, args.team)

    if handle and not args.dry_run:
        driver = build_driver(handle.substrate, dry_run=False)
        await driver.sync_out(handle, team_dir)

    internal = team_dir / "internal"
    if internal.exists():
        shutil.copytree(internal, destination / "internal", dirs_exist_ok=True)
    else:
        (destination / "NO_INTERNAL.txt").write_text("No internal folder exists for this team.\n", encoding="utf-8")

    with db.session(db_path) as conn:
        db.record_event(
            conn,
            team_name=args.team,
            source="hr.inspect_team",
            kind="inspected",
            state="inspected",
            payload_path=str(destination),
            metadata={"dry_run": args.dry_run},
        )
    return {"inspection": str(destination)}


def main(argv: list[str] | None = None) -> None:
    result = asyncio.run(run(build_parser().parse_args(argv)))
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
