from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from harness import db
from harness.tools import dispatch_team, spawn_team
from harness.viewer import auth
from harness.viewer.data import assignment_detail, dashboard, graph, hub_config, team_detail


def test_viewer_session_cookie_round_trip() -> None:
    cookie = auth.issue_session("secret", now=1)
    assert auth.verify_session("secret", cookie, max_age_seconds=10**12)
    assert not auth.verify_session("other-secret", cookie, max_age_seconds=10**12)
    assert auth.code_matches("open-sesame", "open-sesame")
    assert not auth.code_matches("open-sesame", "wrong")


def test_viewer_data_reads_factory_and_sqlite(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    asyncio.run(
        spawn_team.run(
            spawn_team.build_parser().parse_args(
                [
                    "research",
                    "--factory",
                    str(factory),
                    "--substrate",
                    "external",
                    "--dry-run",
                    "--brief",
                    "Find facts.",
                ]
            )
        )
    )
    dispatch_team.run(
        dispatch_team.build_parser().parse_args(
            [
                "research",
                "--factory",
                str(factory),
                "--assignment-id",
                "asn-view",
                "--title",
                "Viewer task",
                "--body",
                "Show this in the viewer.",
            ]
        )
    )

    db_path = db.default_db_path(factory)
    digest = dashboard(factory, db_path)
    assert digest["counts"]["teams"] == 1
    assert digest["counts"]["active_assignments"] == 1
    assert digest["teams"][0]["team_name"] == "research"

    team = team_detail(factory, db_path, "research")
    assert team is not None
    assert "Find facts." in team["brief"]
    assert team["assignments"][0]["assignment_id"] == "asn-view"

    assignment = assignment_detail(factory, db_path, "asn-view")
    assert assignment is not None
    assert "Show this in the viewer." in assignment["body"]

    graph_data = graph(factory, db_path)
    node_ids = {node["id"] for node in graph_data["nodes"]}
    assert "team:research" in node_ids
    assert "assignment:asn-view" in node_ids


def test_hub_config_falls_back_to_repo_templates_for_empty_factory(tmp_path: Path) -> None:
    config = hub_config(tmp_path / "factory")
    assert config["using_fallback"] is True
    assert any(file["name"] == "docs/team/03_top_tier_souls.md" for file in config["fallback"])


def test_hub_config_prefers_live_factory_files(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    factory.mkdir()
    (factory / "README.md").write_text("# Live Hub\n", encoding="utf-8")
    config = hub_config(factory)
    assert config["using_fallback"] is False
    assert config["live"][0]["name"] == "README.md"
    assert "Live Hub" in config["live"][0]["body"]
