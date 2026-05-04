from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from harness import db
from harness.tools import dispatch_team, query_remote_teams, spawn_team, sunset_team


def args(**kwargs):
    return argparse.Namespace(**kwargs)


def base_args(tmp_path: Path, **overrides):
    data = {
        "factory": str(tmp_path / "factory"),
        "db": str(tmp_path / "harness.sqlite3"),
    }
    data.update(overrides)
    return args(**data)


def test_spawn_dispatch_query_and_sunset_external(tmp_path: Path):
    spawn_result = asyncio.run(
        spawn_team.run(
            base_args(
                tmp_path,
                name="dev",
                template="single-agent",
                substrate="external",
                dry_run=True,
                agent_card_url="http://team.example/.well-known/agent-card.json",
                push_url="https://boss.example/a2a/push",
                brief="Build small changes.",
                criteria="Return tested patches.",
                timeout_seconds=30,
            )
        )
    )

    team_dir = Path(spawn_result["path"])
    assert (team_dir / "brief.md").exists()
    transport = json.loads((team_dir / "transport.json").read_text())
    assert transport["team_bearer_token_ref"] == "env://HARNESS_TEAM_DEV_BEARER_TOKEN"
    assert transport["substrate_handle_ref"] == "sqlite://substrate_handles/dev"
    assert "TOKEN" not in (team_dir / "journal.md").read_text()

    dispatch_result = dispatch_team.run(
        base_args(
            tmp_path,
            team="dev",
            assignment_id="asn_test",
            order_id="ord_test",
            title="Patch",
            body="Do the thing.",
            file=None,
        )
    )
    assert Path(dispatch_result["path"]).exists()

    digest = query_remote_teams.run(base_args(tmp_path, team=None, stale_minutes=5, json=True))
    assert digest["teams"][0]["team_name"] == "dev"
    assert digest["teams"][0]["active_assignments"] == 1

    sunset_result = asyncio.run(
        sunset_team.run(base_args(tmp_path, team="dev", dry_run=True, no_archive=False))
    )
    assert "teams_dev_" in sunset_result["archive"]

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        handle = conn.execute("SELECT status FROM substrate_handles WHERE team_name = 'dev'").fetchone()
    assert handle["status"] == "archived"
