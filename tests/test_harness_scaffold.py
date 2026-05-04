from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from harness import db
from harness.substrate.e2b import E2BDriver, E2BUnavailableError
from harness.tools import dispatch_team, inspect_team, query_remote_teams, spawn_team, sunset_team


def test_init_db_creates_required_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert {"team_assignments", "team_events", "substrate_handles"}.issubset(tables)


def test_spawn_external_team_writes_factory_contract_and_handle(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    result = asyncio.run(
        spawn_team.run(
            spawn_team.build_parser().parse_args(
                [
                    "development",
                    "--factory",
                    str(factory),
                    "--substrate",
                    "external",
                    "--agent-card-url",
                    "http://127.0.0.1:8000/.well-known/agent-card.json",
                    "--brief",
                    "Build features.",
                ]
            )
        )
    )

    team_dir = factory / "teams" / "development"
    transport = json.loads((team_dir / "transport.json").read_text(encoding="utf-8"))
    assert result["team"] == "development"
    assert transport["agent_card_url"] == "http://127.0.0.1:8000/.well-known/agent-card.json"
    assert transport["team_bearer_token_ref"] == "env://HARNESS_TEAM_DEVELOPMENT_BEARER_TOKEN"
    assert "Build features." in (team_dir / "brief.md").read_text(encoding="utf-8")

    with db.connect(factory / "harness.sqlite3") as conn:
        handle = db.load_substrate_handle(conn, "development")
        assert handle is not None
        assert handle.substrate == "external"


def test_dispatch_records_assignment_and_query_digest(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    asyncio.run(spawn_team.run(spawn_team.build_parser().parse_args(["qa", "--factory", str(factory), "--substrate", "external"])))

    result = dispatch_team.run(
        dispatch_team.build_parser().parse_args(
            [
                "qa",
                "--factory",
                str(factory),
                "--assignment-id",
                "asn-1",
                "--title",
                "Check release",
                "--body",
                "Run the release checklist.",
            ]
        )
    )

    assert Path(result["path"]).exists()
    digest = query_remote_teams.run(query_remote_teams.build_parser().parse_args(["--factory", str(factory)]))
    assert digest["teams"][0]["team_name"] == "qa"
    assert digest["teams"][0]["active_assignments"] == 1


def test_event_dedupe_returns_none_for_duplicate_sequence(tmp_path: Path) -> None:
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    with db.session(db_path) as conn:
        first = db.record_event(
            conn,
            team_name="research",
            source="a2a-bridge",
            kind="push",
            task_id="task-1",
            sequence=7,
            state="working",
            signature="sig",
        )
        second = db.record_event(
            conn,
            team_name="research",
            source="a2a-bridge",
            kind="push",
            task_id="task-1",
            sequence=7,
            state="working",
            signature="sig",
        )
    assert first is not None
    assert second is None


def test_e2b_driver_is_import_safe_until_real_operation() -> None:
    driver = E2BDriver(dry_run=True)
    handle = asyncio.run(
        driver.provision(
            "dry",
            Path("."),
            spawn_team.load_template("single-agent"),
            1,
        )
    )
    assert handle.handle == "dry-run-e2b://dry"

    real_driver = E2BDriver(api_key=None, dry_run=False)
    with pytest.raises(E2BUnavailableError):
        real_driver._require_sdk()


def test_inspect_and_sunset_work_in_dry_run(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    asyncio.run(
        spawn_team.run(
            spawn_team.build_parser().parse_args(["ops", "--factory", str(factory), "--substrate", "external", "--template", "multi-agent"])
        )
    )

    inspection = asyncio.run(inspect_team.run(inspect_team.build_parser().parse_args(["ops", "--factory", str(factory), "--dry-run"])))
    assert (Path(inspection["inspection"]) / "internal").exists()

    archive = asyncio.run(sunset_team.run(sunset_team.build_parser().parse_args(["ops", "--factory", str(factory), "--dry-run"])))
    assert archive["archive"] != "not archived"
    assert not (factory / "teams" / "ops").exists()


def test_spawn_real_e2b_requires_push_url(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        asyncio.run(
            spawn_team.run(
                spawn_team.build_parser().parse_args(
                    ["team", "--factory", str(tmp_path / "factory"), "--substrate", "e2b"]
                )
            )
        )
