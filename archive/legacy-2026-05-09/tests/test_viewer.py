from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace
from pathlib import Path

from harness import db
from harness.models import SubstrateHandle
from harness.tools import dispatch_team, spawn_team
from harness.tools import control
from harness.viewer import auth
from harness.viewer.server import APP_HTML, ViewerConfig, ViewerServer, _chat_prompt, send_chat_message
from harness.viewer.data import (
    _E2B_PROVIDER_CACHE,
    assignment_detail,
    dashboard,
    execution_ticket_detail,
    graph,
    hub_config,
    resource_detail,
    schedules,
    team_detail,
    user_request_detail,
)


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
    assert "Schedules" in APP_HTML
    assert "Resources" in APP_HTML
    assert "renderKanban" in APP_HTML
    assert "renderSchedules" in APP_HTML
    assert "renderResources" in APP_HTML
    assert "Execution Tickets" in APP_HTML
    assert "Live E2B machines" in APP_HTML
    assert "metric--live-e2b" in APP_HTML
    assert "executionTicketTable" in APP_HTML
    assert "kanbanTicketCard" in APP_HTML
    assert "renderTicket" in APP_HTML
    assert "renderRequest" in APP_HTML
    assert 'path.startsWith("/tickets/")' in APP_HTML
    assert 'path.startsWith("/requests/")' in APP_HTML
    assert "kanban--tickets" in APP_HTML
    assert "kanban-row" in APP_HTML
    assert "renderTabs" in APP_HTML
    assert "compactGraphText" in APP_HTML
    assert "Hermes Chat" in APP_HTML
    assert 'id="chat-window"' in APP_HTML
    assert 'localStorage.getItem(CHAT_STORAGE_KEY)' in APP_HTML
    assert 'postApi("/api/chat"' in APP_HTML
    assert "renderMarkdown" in APP_HTML
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in APP_HTML
    assert "X-Harness-Timezone" in APP_HTML
    assert "function parseHarnessTime" in APP_HTML
    assert "function fmtTime" in APP_HTML
    assert "Times: ${esc(USER_TIME_ZONE)}" in APP_HTML
    assert "${fmtTime(t.last_event_at, \"never\")}" in APP_HTML
    assert "${fmtTime(e.ts)}" in APP_HTML
    assert "${fmtTime(j.next_run_at || \"\")}" in APP_HTML
    assert 'class="tabs"' in APP_HTML
    assert 'path === "/kanban"' in APP_HTML
    assert 'path === "/resources"' in APP_HTML
    assert 'path === "/schedules"' in APP_HTML
    assert 'path === "/graph"' in APP_HTML
    assert "renderOrgGraphSvg({maxAssignmentsPerTeam: 2" in APP_HTML


def test_viewer_chat_prompt_keeps_transcript_context() -> None:
    prompt = _chat_prompt(
        [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Follow up"},
        ]
    )
    assert "Conversation transcript" in prompt
    assert "User:\nFirst question" in prompt
    assert "Assistant:\nFirst answer" in prompt
    assert "Latest user message:\nFollow up" in prompt


def test_viewer_chat_falls_back_to_local_hermes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_VIEWER_CHAT_MANIFEST", raising=False)
    monkeypatch.delenv("HERMES_A2A_MANIFEST", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    hermes = tmp_path / "hermes"
    hermes.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "prompt = sys.argv[sys.argv.index('-z') + 1]\n"
        "print('**fake hermes**\\n\\n' + prompt[-24:])\n",
        encoding="utf-8",
    )
    hermes.chmod(hermes.stat().st_mode | 0o100)
    factory = tmp_path / "factory"
    db_path = db.default_db_path(factory)
    config = ViewerConfig(
        factory=factory,
        db_path=db_path,
        access_code="code",
        cookie_secret="secret",
        hermes_bin=str(hermes),
        chat_model="m",
        chat_timeout_seconds=10,
    )

    result = send_chat_message(config, {"messages": [{"role": "user", "content": "hello **world**"}]})

    assert result["transport"] == "local-hermes"
    assert result["context_id"].startswith("viewer-chat-")
    assert result["message"]["role"] == "assistant"
    assert "**fake hermes**" in result["message"]["content"]


def test_viewer_exposes_keyed_remote_control_api(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    db_path = db.default_db_path(factory)
    db.init_db(db_path)
    server = ViewerServer(
        ("127.0.0.1", 0),
        ViewerConfig(
            factory=factory,
            db_path=db_path,
            access_code="browser-code",
            cookie_secret="secret",
            control_api_key="control-key",
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        body = json.dumps({"argv": ["status", "--json"]}).encode("utf-8")
        request = urllib.request.Request(
            f"{url}/api/control",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("control API should reject missing token")

        result = control.run_remote(
            control.build_parser().parse_args(["--url", url, "--token", "control-key", "status", "--json"]),
            ["--url", url, "--token", "control-key", "status", "--json"],
        )
        assert result["summary"]["teams"] == 0
        assert result["summary"]["waiting_on_user"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_viewer_data_reads_factory_and_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.delenv("E2B_ACCESS_TOKEN", raising=False)
    _E2B_PROVIDER_CACHE.update({"expires_at": 0.0, "summary": None})
    factory = tmp_path / "factory"
    resource_path = factory / "resources" / "website" / "main.json"
    resource_path.parent.mkdir(parents=True)
    resource_path.write_text(
        """
        {
          "id": "website/main",
          "title": "Main website",
          "kind": "website",
          "state": "ready",
          "owner": "dev",
          "approval_policy": "production mutations require explicit approval"
        }
        """,
        encoding="utf-8",
    )
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
        db.upsert_execution_ticket(
            conn,
            ticket_id="tkt-approval-view",
            title="Approve publish",
            mode="escalate",
            team_name="research",
            status="blocked",
            priority=5,
            body="Approve this external action.",
            assignment_id="tkt-approval-view",
            approval_request_id="tkt-approval-view:approval-required",
            acceptance=["approval is recorded"],
            verification=["request card opens"],
            metadata={
                "resources": ["website/main"],
                "approval": {
                    "requested_action": "publish prepared copy",
                    "target_resource": "website/main",
                    "why": "validate website conversion copy",
                    "blast_radius": "public website content",
                    "rollback": "restore previous copy",
                },
            },
        )
        db.upsert_approval_request(
            conn,
            request_id="tkt-approval-view:approval-required",
            assignment_id="tkt-approval-view",
            team_name="research",
            task_id="task-approval-view",
            kind="approval-required",
            title="Approve publish",
            prompt="Approve publishing this prepared artifact.",
            required_fields=[{"name": "approved"}],
            escalation_path=str(factory / "escalations" / "tkt-approval-view.md"),
            metadata={"ticket_id": "tkt-approval-view", "resources": ["website/main"]},
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
        db.save_assignment_sandbox(
            conn,
            assignment_id="asn-real-e2b",
            team_name="research",
            handle=SubstrateHandle(
                team_name="research",
                substrate="e2b",
                handle="sandbox-real-1",
                metadata={"workspace_path": str(factory / "teams" / "research")},
            ),
            agent_card_url="https://sandbox-real-1.example/.well-known/agent-card.json",
            status="booted",
        )
        db.save_assignment_sandbox(
            conn,
            assignment_id="asn-dry-e2b",
            team_name="research",
            handle=SubstrateHandle(
                team_name="research",
                substrate="e2b",
                handle="dry-run-e2b://research",
                metadata={"dry_run": True},
            ),
            agent_card_url="http://localhost/.well-known/agent-card.json",
            status="booted",
            metadata={"dry_run": True},
        )
        db.save_assignment_sandbox(
            conn,
            assignment_id="asn-placeholder-e2b",
            team_name="research",
            handle=SubstrateHandle(
                team_name="research",
                substrate="e2b",
                handle="e2b-team://research",
                metadata={"per_assignment": True},
            ),
            agent_card_url=None,
            status="booted",
        )

    digest = dashboard(factory, db_path)
    assert digest["counts"]["teams"] == 1
    assert digest["counts"]["active_e2b_machines"] == 1
    assert digest["counts"]["resources"] == 1
    assert digest["e2b_machines"]["active"] == 1
    assert digest["e2b_machines"]["teams"] == ["research"]
    assert digest["counts"]["active_assignments"] == 1
    assert digest["counts"]["waiting_on_user"] == 2
    assert digest["counts"]["open_alerts"] == 1
    assert digest["teams"][0]["team_name"] == "research"
    assert digest["teams"][0]["open_user_requests"] == 2
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

    ticket = execution_ticket_detail(factory, db_path, "tkt-approval-view")
    assert ticket is not None
    assert ticket["assignment"] is None
    assert ticket["user_requests"][0]["request_id"] == "tkt-approval-view:approval-required"
    assert ticket["resources"][0]["id"] == "website/main"

    request = user_request_detail(factory, db_path, "tkt-approval-view:approval-required")
    assert request is not None
    assert request["assignment"] is None
    assert request["ticket"]["ticket_id"] == "tkt-approval-view"
    assert request["resources"][0]["id"] == "website/main"
    assert request["decision"]["requested_action"] == "publish prepared copy"

    resource = resource_detail(factory, "website/main")
    assert resource is not None
    assert resource["title"] == "Main website"

    graph_data = graph(factory, db_path)
    node_ids = {node["id"] for node in graph_data["nodes"]}
    assert "team:research" in node_ids
    assert "assignment:asn-view" in node_ids


def test_dashboard_prefers_live_e2b_provider_count(tmp_path: Path, monkeypatch) -> None:
    factory = tmp_path / "factory"
    db_path = db.default_db_path(factory)
    db.init_db(db_path)
    with db.session(db_path) as conn:
        db.save_assignment_sandbox(
            conn,
            assignment_id="dead-in-db",
            team_name="research",
            handle=SubstrateHandle(team_name="research", substrate="e2b", handle="dead-sandbox"),
            agent_card_url=None,
            status="booted",
        )

    class FakePaginator:
        def __init__(self) -> None:
            self._done = False

        @property
        def has_next(self) -> bool:
            return not self._done

        def next_items(self) -> list[SimpleNamespace]:
            self._done = True
            return [SimpleNamespace(sandbox_id="live-a"), SimpleNamespace(sandbox_id="live-b")]

    class FakeSandbox:
        @staticmethod
        def list(**_: object) -> FakePaginator:
            return FakePaginator()

    class FakeQuery:
        def __init__(self, **_: object) -> None:
            pass

    fake_e2b = SimpleNamespace(
        Sandbox=FakeSandbox,
        SandboxQuery=FakeQuery,
        SandboxState=SimpleNamespace(RUNNING="running"),
    )
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "e2b", fake_e2b)
    _E2B_PROVIDER_CACHE.update({"expires_at": 0.0, "summary": None})

    digest = dashboard(factory, db_path)
    assert digest["counts"]["active_e2b_machines"] == 2
    assert digest["e2b_machines"]["database_active"] == 1
    assert digest["e2b_machines"]["source"] == "provider"


def test_hub_config_falls_back_to_repo_templates_for_empty_factory(tmp_path: Path) -> None:
    config = hub_config(tmp_path / "factory")
    assert config["using_fallback"] is True
    assert any(file["name"] == "docs/boss-team-contract.md" for file in config["fallback"])


def test_hub_config_prefers_live_factory_files(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    factory.mkdir()
    (factory / "README.md").write_text("# Live Hub\n", encoding="utf-8")
    config = hub_config(factory)
    assert config["using_fallback"] is False
    assert config["live"][0]["name"] == "README.md"
    assert "Live Hub" in config["live"][0]["body"]


def test_schedules_reads_profile_cron_jobs(tmp_path: Path) -> None:
    jobs_path = tmp_path / "profiles" / "boss" / "cron" / "jobs.json"
    jobs_path.parent.mkdir(parents=True)
    jobs_path.write_text(
        """
        {
          "updated_at": "2026-05-05T23:37:00+00:00",
          "jobs": [
            {
              "id": "job-1",
              "name": "execution-board-tick",
              "script": "execution_board_tick.py",
              "no_agent": true,
              "schedule": {"display": "every 10m"},
              "schedule_display": "every 10m",
              "repeat": {"times": null, "completed": 3},
              "enabled": true,
              "state": "scheduled",
              "next_run_at": "2026-05-05T23:47:00+00:00",
              "last_run_at": "2026-05-05T23:37:00+00:00",
              "last_status": "ok",
              "deliver": "local",
              "workdir": "/opt/hermes-harness"
            },
            {
              "id": "job-2",
              "name": "paused-job",
              "schedule_display": "every 1h",
              "repeat": {"times": 5, "completed": 1},
              "enabled": false,
              "state": "paused",
              "paused_reason": "manual"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    data = schedules(tmp_path)

    assert data["counts"] == {"jobs": 2, "active": 1, "paused": 1, "last_failed": 0}
    assert data["stores"] == [{"profile": "boss", "path": str(jobs_path)}]
    assert data["updated_at"]["boss"] == "2026-05-05T23:37:00+00:00"
    active = data["jobs"][0]
    assert active["profile"] == "boss"
    assert active["job_id"] == "job-1"
    assert active["schedule"] == "every 10m"
    assert active["script"] == "execution_board_tick.py"
    assert active["no_agent"] is True
