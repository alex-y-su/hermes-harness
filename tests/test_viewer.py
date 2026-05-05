from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from harness import db
from harness.tools import dispatch_team, spawn_team
from harness.viewer import auth
from harness.viewer.server import APP_HTML
from harness.viewer.data import assignment_detail, dashboard, graph, hub_config, team_detail


def test_viewer_session_cookie_round_trip() -> None:
    cookie = auth.issue_session("secret", now=1)
    assert auth.verify_session("secret", cookie, max_age_seconds=10**12)
    assert not auth.verify_session("other-secret", cookie, max_age_seconds=10**12)
    assert auth.code_matches("open-sesame", "open-sesame")
    assert not auth.code_matches("open-sesame", "wrong")


def test_dashboard_embeds_graph_and_keeps_full_graph_route() -> None:
    assert "dashboard-graph" in APP_HTML
    assert "Open full graph" in APP_HTML
    assert "Waiting on User" in APP_HTML
    assert "userRequestTable" in APP_HTML
    assert "Kanban" in APP_HTML
    assert "renderKanban" in APP_HTML
    assert "renderTabs" in APP_HTML
    assert 'class="tabs"' in APP_HTML
    assert 'path === "/kanban"' in APP_HTML
    assert 'path === "/graph"' in APP_HTML
    assert "renderOrgGraphSvg({maxAssignmentsPerTeam: 2" in APP_HTML


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
    with db.session(db_path) as conn:
        db.upsert_approval_request(
            conn,
            request_id="asn-view:auth-required",
            assignment_id="asn-view",
            team_name="research",
            task_id="task-view",
            kind="auth-required",
            title="OAuth required",
            prompt="Authorize the docs provider.",
            required_fields=[{"name": "provider"}],
            escalation_path=str(factory / "escalations" / "asn-view.md"),
            metadata={"source": "test"},
        )
        db.upsert_approval_request(
            conn,
            request_id="asn-view:input-required",
            assignment_id="asn-view",
            team_name="research",
            task_id="task-view",
            kind="input-required",
            status="resuming",
            title="Input supplied",
            prompt="Use the supplied target.",
            required_fields=[{"name": "target"}],
            response={"target": "docs"},
            escalation_path=str(factory / "escalations" / "asn-view-input.md"),
            metadata={"source": "test"},
        )
        db.upsert_assignment_resume(
            conn,
            resume_id="resume-view",
            request_id="asn-view:input-required",
            parent_assignment_id="asn-view",
            continuation_assignment_id="asn-view-resume",
            team_name="research",
            status="sent",
            response={"target": "docs"},
            strategy="continuation_assignment",
        )
        db.upsert_operator_alert(
            conn,
            alert_id="alert-view",
            dedupe_key="test:alert-view",
            severity="warning",
            kind="assignment-stale",
            team_name="research",
            assignment_id="asn-view",
            title="Assignment stale",
            body="No heartbeat.",
        )

    digest = dashboard(factory, db_path)
    assert digest["counts"]["teams"] == 1
    assert digest["counts"]["active_assignments"] == 1
    assert digest["counts"]["waiting_on_user"] == 1
    assert digest["counts"]["open_alerts"] == 1
    assert digest["teams"][0]["team_name"] == "research"
    assert digest["teams"][0]["open_user_requests"] == 1
    request_ids = {request["request_id"] for request in digest["user_requests"]}
    assert "asn-view:auth-required" in request_ids
    assert any(request["status"] == "resuming" for request in digest["user_requests"])

    team = team_detail(factory, db_path, "research")
    assert team is not None
    assert "Find facts." in team["brief"]
    assert team["assignments"][0]["assignment_id"] == "asn-view"
    assert any(request["kind"] == "auth-required" for request in team["user_requests"])
    assert team["alerts"][0]["alert_id"] == "alert-view"

    assignment = assignment_detail(factory, db_path, "asn-view")
    assert assignment is not None
    assert "Show this in the viewer." in assignment["body"]
    assert any(request["title"] == "OAuth required" for request in assignment["user_requests"])
    assert assignment["resumes"][0]["resume_id"] == "resume-view"
    assert assignment["alerts"][0]["alert_id"] == "alert-view"

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
