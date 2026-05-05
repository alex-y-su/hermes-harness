from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from harness import db
from harness.factory import team_path
from harness.models import SubstrateHandle
from harness.substrate.factory import build_driver
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync, archive, and stop one per-assignment sandbox.")
    add_factory_args(parser)
    parser.add_argument("team")
    parser.add_argument("assignment_id")
    parser.add_argument("--terminal-state", default="completed")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


async def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    return await finalize_assignment(
        factory=factory,
        db_path=db_path,
        team=args.team,
        assignment_id=args.assignment_id,
        terminal_state=args.terminal_state,
        dry_run=args.dry_run,
    )


async def finalize_assignment(
    *,
    factory: Path,
    db_path: Path,
    team: str,
    assignment_id: str,
    terminal_state: str = "completed",
    dry_run: bool = False,
    api_key: str | None = None,
) -> dict[str, str]:
    team_dir = team_path(factory, team)
    with db.session(db_path) as conn:
        row = db.load_assignment_sandbox(conn, assignment_id)
        if row is None:
            return {"team_name": team, "assignment_id": assignment_id, "status": "missing"}
        handle_data = json.loads(row["handle"])
        metadata = handle_data.get("metadata") or {}
        handle = SubstrateHandle(
            team_name=handle_data["team_name"],
            substrate=handle_data["substrate"],
            handle=handle_data["handle"],
            metadata=metadata,
        )
        should_dry_run = dry_run or bool(metadata.get("dry_run"))
        db.mark_assignment_sandbox_terminal(conn, assignment_id, terminal_state)

    driver = build_driver(handle.substrate, dry_run=should_dry_run, api_key=api_key)
    archive_path = factory / "archive" / "assignment_sandboxes" / f"{team}_{assignment_id}_{_timestamp()}"
    if not should_dry_run:
        await driver.sync_out(handle, team_dir)
        await driver.cancel(handle)
    await driver.archive(handle, archive_path)

    manifest_path = archive_path / "assignment-sandbox.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "team_name": team,
                "assignment_id": assignment_id,
                "terminal_state": terminal_state,
                "handle": asdict(handle),
                "dry_run": should_dry_run,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with db.session(db_path) as conn:
        db.mark_assignment_sandbox_archived(conn, assignment_id, archive_path=str(archive_path))
        db.record_event(
            conn,
            team_name=team,
            assignment_id=assignment_id,
            source="finalize_assignment_sandbox",
            kind="assignment-sandbox-archived",
            state="archived",
            payload_path=str(manifest_path),
            metadata={"terminal_state": terminal_state, "dry_run": should_dry_run},
        )

    return {
        "team_name": team,
        "assignment_id": assignment_id,
        "status": "archived",
        "archive": str(archive_path),
    }


def main(argv: list[str] | None = None) -> None:
    result = asyncio.run(run(build_parser().parse_args(argv)))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
