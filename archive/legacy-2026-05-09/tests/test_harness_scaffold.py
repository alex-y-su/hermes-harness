from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from harness import db
from harness.substrate.e2b import (
    DEFAULT_TEMPLATE_ALIAS,
    E2BDriver,
    E2BUnavailableError,
    discover_codex_auth_file,
    filtered_llm_env,
    list_remote_files,
    resolve_template_alias,
)
from harness.tools import dispatch_team, inspect_team, query_remote_teams, spawn_team, sunset_team


def test_init_db_creates_required_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(team_assignments)")}

    assert {
        "team_assignments",
        "team_events",
        "substrate_handles",
        "assignment_sandboxes",
        "approval_requests",
        "execution_tickets",
        "orchestrator_leases",
        "assignment_resumes",
        "operator_alerts",
    }.issubset(tables)
    assert {
        "status_reason",
        "blocked_by",
        "retry_count",
        "next_retry_at",
        "lease_owner",
        "lease_expires_at",
        "last_heartbeat_at",
        "last_error",
    }.issubset(columns)


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


def test_e2b_driver_is_import_safe_until_real_operation(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.delenv("E2B_API_KEY", raising=False)
    real_driver = E2BDriver(api_key=None, dry_run=False)
    with pytest.raises(E2BUnavailableError):
        real_driver._require_sdk()


def test_e2b_template_alias_resolution_and_env_filtering(tmp_path: Path) -> None:
    team = tmp_path / "team"
    (team / "e2b").mkdir(parents=True)
    (team / "e2b" / "template.json").write_text(
        json.dumps(
            {
                "default_alias": DEFAULT_TEMPLATE_ALIAS,
                "team_alias": "team-heavy-template",
                "active_template": "team-active-template",
            }
        ),
        encoding="utf-8",
    )

    assert resolve_template_alias(team) == "team-active-template"

    env = {
        "OPENAI_API_KEY": "must-not-copy",
        "OPENROUTER_API_KEY": "must-not-copy",
        "HERMES_INFERENCE_PROVIDER": "openai-codex",
        "HERMES_HOME": "/tmp/hermes",
        "LLM_BASE_URL": "must-not-copy",
        "MODEL_DEFAULT": "gpt-5.5",
        "UNRELATED": "ignored",
    }
    assert filtered_llm_env(env) == {
        "HERMES_INFERENCE_PROVIDER": "openai-codex",
        "HERMES_HOME": "/tmp/hermes",
        "MODEL_DEFAULT": "gpt-5.5",
    }


def test_codex_auth_file_discovery_prefers_explicit_override(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit-auth.json"
    explicit.write_text("{}", encoding="utf-8")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text('{"ignored": true}', encoding="utf-8")

    assert discover_codex_auth_file({"HERMES_CODEX_AUTH_FILE": str(explicit), "CODEX_HOME": str(codex_home)}) == explicit


def test_codex_auth_file_discovery_uses_codex_home(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    auth = codex_home / "auth.json"
    auth.write_text("{}", encoding="utf-8")

    assert discover_codex_auth_file({"CODEX_HOME": str(codex_home)}) == auth


def test_e2b_remote_file_listing_skips_entryinfo_directories() -> None:
    class EntryType:
        def __init__(self, value: str) -> None:
            self.value = value

    class Entry:
        def __init__(self, path: str, value: str) -> None:
            self.path = path
            self.name = Path(path).name
            self.type = EntryType(value)

    class Files:
        def __init__(self) -> None:
            self.visited: list[str] = []

        def list(self, path: str) -> list[Entry]:
            self.visited.append(path)
            return {
                "/home/user/workspace": [
                    Entry("/home/user/workspace/context", "dir"),
                    Entry("/home/user/workspace/brief.md", "file"),
                    Entry("/home/user/workspace/.harness", "dir"),
                ],
                "/home/user/workspace/context": [
                    Entry("/home/user/workspace/context/note.md", "file"),
                ],
            }.get(path, [])

    files = Files()

    assert sorted(list_remote_files(files, "/home/user/workspace")) == [
        "/home/user/workspace/brief.md",
        "/home/user/workspace/context/note.md",
    ]
    assert "/home/user/workspace/.harness" not in files.visited


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


def test_spawn_e2b_registers_per_assignment_team_without_booting_sandbox(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    result = asyncio.run(
        spawn_team.run(
            spawn_team.build_parser().parse_args(
                [
                    "workers",
                    "--factory",
                    str(factory),
                    "--substrate",
                    "e2b",
                    "--dry-run",
                    "--push-url",
                    "https://boss.example/a2a/push",
                ]
            )
        )
    )

    team_dir = Path(result["path"])
    transport = json.loads((team_dir / "transport.json").read_text(encoding="utf-8"))
    assert transport["substrate"] == "e2b"
    assert transport["per_assignment"] is True
    assert transport["agent_card_url"] == ""

    with db.connect(factory / "harness.sqlite3") as conn:
        handle = db.load_substrate_handle(conn, "workers")
    assert handle is not None
    assert handle.handle == "e2b-team://workers"
    assert handle.metadata["per_assignment"] is True
