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
        "blueprint": None,
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
    assert digest["stale"] == []

    sunset_result = asyncio.run(
        sunset_team.run(base_args(tmp_path, team="dev", dry_run=True, no_archive=False))
    )
    assert "teams_dev_" in sunset_result["archive"]

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        handle = conn.execute("SELECT status FROM substrate_handles WHERE team_name = 'dev'").fetchone()
    assert handle["status"] == "archived"


def test_tools_default_factory_uses_factory_dir_env(tmp_path: Path, monkeypatch) -> None:
    factory = tmp_path / "mounted-factory"
    monkeypatch.delenv("HARNESS_FACTORY", raising=False)
    monkeypatch.setenv("FACTORY_DIR", str(factory))

    spawn_result = asyncio.run(
        spawn_team.run(
            spawn_team.build_parser().parse_args(
                [
                    "chat-created",
                    "--substrate",
                    "external",
                    "--dry-run",
                    "--agent-card-url",
                    "http://team.example/.well-known/agent-card.json",
                ]
            )
        )
    )

    assert Path(spawn_result["path"]).is_relative_to(factory)
    assert (factory / "teams" / "chat-created" / "status.json").exists()


def test_spawn_team_from_blueprint_directory(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    blueprint = factory / "team_blueprints" / "creators"
    blueprint.mkdir(parents=True)
    (blueprint / "blueprint.yaml").write_text(
        "name: creators\nsubstrate: e2b\ntemplate: multi-agent-team\n",
        encoding="utf-8",
    )
    (blueprint / "brief.md").write_text("# Creators Brief\n\nRecruit creators.\n", encoding="utf-8")
    (blueprint / "TEAM_SOUL.md").write_text("# Creators Soul\n\nRun on E2B.\n", encoding="utf-8")
    (blueprint / "criteria.md").write_text("# Criteria\n\nReport partnership artifacts.\n", encoding="utf-8")
    (blueprint / "AGENTS.md").write_text("# Agents\n\nUse A2A.\n", encoding="utf-8")

    parsed = spawn_team.build_parser().parse_args(
        [
            "--factory",
            str(factory),
            "--db",
            str(tmp_path / "harness.sqlite3"),
            "creators",
            "--substrate",
            "external",
            "--dry-run",
            "--agent-card-url",
            "http://team.example/.well-known/agent-card.json",
            "--blueprint",
            "creators",
            "--template",
            "multi-agent",
        ]
    )
    assert parsed.blueprint == "creators"

    result = asyncio.run(spawn_team.run(parsed))

    team_dir = Path(result["path"])
    assert (team_dir / "context" / "hiring_blueprint.md").exists()
    assert "Recruit creators" in (team_dir / "brief.md").read_text(encoding="utf-8")
    assert "Run on E2B" in (team_dir / "TEAM_SOUL.md").read_text(encoding="utf-8")
    status = json.loads((team_dir / "status.json").read_text(encoding="utf-8"))
    assert status["template"] == "multi-agent-team"
    assert status["blueprint"] == "creators"
    transport = json.loads((team_dir / "transport.json").read_text(encoding="utf-8"))
    assert transport["protocol"] == "a2a"
    assert transport["substrate"] == "external"
    assert transport["blueprint"] == "creators"
    assert transport["substrate_handle_ref"] == "sqlite://substrate_handles/creators"

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        row = conn.execute("SELECT metadata FROM team_events WHERE team_name = 'creators'").fetchone()
    metadata = json.loads(row["metadata"])
    assert metadata["template"] == "multi-agent-team"
    assert metadata["blueprint"] == "creators"
