from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from harness import db
from harness.models import SubstrateHandle
from harness.tools import (
    ack_alert,
    cancel_assignment,
    control,
    explain_blockers,
    execution_board,
    orchestrator,
    query_alerts,
    query_remote_teams,
    request_resources,
    resource_gate,
    run_soak,
    query_user_requests,
    query_work_board,
    requeue_assignment,
    resolve_user_request,
    dispatch_team,
    spawn_team,
    sunset_team,
)
from harness.tools.run_assignment_sandbox import run_for_assignment


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


def test_request_resources_creates_user_requests_once(tmp_path: Path):
    factory = tmp_path / "factory"
    ready = factory / "resources" / "website" / "main.json"
    blocked = factory / "resources" / "social" / "main.json"
    ready.parent.mkdir(parents=True)
    blocked.parent.mkdir(parents=True)
    ready.write_text(
        json.dumps(
            {
                "id": "website/main",
                "title": "Main website",
                "kind": "website",
                "state": "ready",
                "owner": "dev",
            }
        ),
        encoding="utf-8",
    )
    blocked.write_text(
        json.dumps(
            {
                "id": "social/main",
                "title": "Main social channels",
                "kind": "external_accounts",
                "state": "needs-access",
                "owner": "growth",
            }
        ),
        encoding="utf-8",
    )

    first = request_resources.run(base_args(tmp_path, tag="first", json=True))
    second = request_resources.run(base_args(tmp_path, tag="second", json=True))

    assert first["created"] == ["resource-social-main-required-first"]
    assert second["created"] == []
    assert second["existing"] == ["resource-social-main-required-first"]
    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        requests = db.list_approval_requests(conn, status="open")
    assert len(requests) == 1
    assert requests[0]["kind"] == "resource-required"
    assert json.loads(blocked.read_text())["user_request_id"] == "resource-social-main-required-first"


def test_resource_gate_reserves_and_blocks_depleted_social_resource(tmp_path: Path):
    factory = tmp_path / "factory"
    resource = factory / "resources" / "social" / "x-main.json"
    resource.parent.mkdir(parents=True)
    resource.write_text(
        json.dumps(
            {
                "id": "social/x-main",
                "title": "Main X account",
                "kind": "social_account",
                "state": "ready",
                "approval_policy": "public posts require explicit approval",
                "usage_policy": {
                    "actions": {
                        "post_public": {
                            "max_per_24h": 1,
                            "reservation_ttl_minutes": 15,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    first = resource_gate.run(
        base_args(
            tmp_path,
            command="reserve",
            resource="social/x-main",
            action="post_public",
            ticket_id="tkt-one",
            artifact="/factory/teams/brand/outbox/post.md",
            now="2026-05-06T12:00:00Z",
            json=True,
        )
    )

    assert first["decision"] == "requires_approval"
    assert first["reservation_id"].startswith("rsv-")
    assert Path(first["decision_path"]).exists()
    ledger = factory / "resource_usage" / "social" / "x-main.jsonl"
    assert json.loads(ledger.read_text().splitlines()[0])["status"] == "reserved"

    blocked = resource_gate.run(
        base_args(
            tmp_path,
            command="check",
            resource="social/x-main",
            action="post_public",
            ticket_id="tkt-two",
            artifact=None,
            now="2026-05-06T12:05:00Z",
            json=True,
        )
    )

    assert blocked["decision"] == "blocked"
    assert blocked["reason"] == "quota_depleted"
    assert blocked["available_at"] == "2026-05-06T12:15:00Z"

    released = resource_gate.run(
        base_args(
            tmp_path,
            command="release",
            resource="social/x-main",
            action="post_public",
            ticket_id="tkt-one",
            reservation_id=first["reservation_id"],
            reason="approval denied",
            json=True,
        )
    )
    assert released["status"] == "released"

    allowed_again = resource_gate.run(
        base_args(
            tmp_path,
            command="check",
            resource="social/x-main",
            action="post_public",
            ticket_id="tkt-two",
            artifact=None,
            now="2026-05-06T12:05:00Z",
            json=True,
        )
    )
    assert allowed_again["decision"] == "requires_approval"


def test_resource_gate_cooldown_quiet_hours_and_cards(tmp_path: Path):
    factory = tmp_path / "factory"
    resource = factory / "resources" / "websites" / "roomcord-com.json"
    resource.parent.mkdir(parents=True)
    resource.write_text(
        json.dumps(
            {
                "id": "websites/roomcord-com",
                "title": "Roomcord website",
                "kind": "website",
                "state": "ready",
                "approval_policy": "production mutations require explicit approval",
                "usage_policy": {
                    "actions": {
                        "change_page_title": {
                            "max_per_30d": 2,
                            "observation_window_days": 21,
                            "quiet_hours_local": {
                                "start": "22:00",
                                "end": "08:00",
                                "timezone": "UTC",
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    resource_gate.run(
        base_args(
            tmp_path,
            command="commit",
            resource="websites/roomcord-com",
            action="change_page_title",
            ticket_id="tkt-old",
            reservation_id=None,
            external_ref="git:abc",
            metadata=None,
            json=True,
        )
    )
    ledger = factory / "resource_usage" / "websites" / "roomcord-com.jsonl"
    entry = json.loads(ledger.read_text().splitlines()[0])
    entry["ts"] = "2026-05-01T10:00:00Z"
    ledger.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")

    cooldown = resource_gate.run(
        base_args(
            tmp_path,
            command="check",
            resource="websites/roomcord-com",
            action="change_page_title",
            ticket_id="tkt-new",
            artifact=None,
            now="2026-05-06T12:00:00Z",
            json=True,
        )
    )
    assert cooldown["decision"] == "blocked"
    assert cooldown["reason"] == "cooldown"
    assert cooldown["available_at"] == "2026-05-22T10:00:00Z"

    quiet = resource_gate.run(
        base_args(
            tmp_path,
            command="check",
            resource="websites/roomcord-com",
            action="change_page_title",
            ticket_id="tkt-night",
            artifact=None,
            now="2026-06-01T23:00:00Z",
            json=True,
        )
    )
    assert quiet["decision"] == "blocked"
    assert quiet["reason"] == "quiet_hours"
    assert quiet["available_at"] == "2026-06-02T08:00:00Z"

    card = resource_gate.run(
        base_args(
            tmp_path,
            command="card",
            card_command="create",
            resource="websites/roomcord-com",
            action="change_page_title",
            ticket_id="tkt-new",
            team="dev",
            artifact="/factory/teams/dev/outbox/title.md",
            why="test SEO title",
            title=None,
            metadata=None,
            json=True,
        )
    )
    assert Path(card["path"]).parent.name == "pending"
    gated = resource_gate.run(
        base_args(
            tmp_path,
            command="card",
            card_command="gate",
            card=card["card"]["card_id"],
            now="2026-05-06T12:00:00Z",
            json=True,
        )
    )
    assert Path(gated["path"]).parent.name == "blocked"
    assert gated["decision"]["reason"] == "cooldown"


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
    assert digest["teams"][0]["open_user_requests"] == 0
    assert digest["stale"] == []

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        db.upsert_approval_request(
            conn,
            request_id="asn_test:input-required",
            assignment_id="asn_test",
            team_name="dev",
            task_id="task-1",
            kind="input-required",
            title="Need target",
            prompt="Which target should I use?",
            required_fields=[{"name": "target"}],
            escalation_path=str(tmp_path / "factory" / "escalations" / "request.md"),
            metadata={"source": "test"},
        )

    digest = query_remote_teams.run(base_args(tmp_path, team=None, stale_minutes=5, json=True))
    assert digest["teams"][0]["open_user_requests"] == 1
    assert digest["user_requests"][0]["request_id"] == "asn_test:input-required"

    open_requests = query_user_requests.run(base_args(tmp_path, status="open", team=None, assignment_id=None, json=True))
    assert open_requests["count"] == 1
    assert open_requests["requests"][0]["required_fields"] == [{"name": "target"}]

    supplied = resolve_user_request.run(
        base_args(
            tmp_path,
            request_id="asn_test:input-required",
            response_json='{"target":"staging"}',
            status="supplied",
            no_continuation=False,
            continuation_assignment_id=None,
        )
    )
    assert supplied["status"] == "resuming"
    assert supplied["response"] == {"target": "staging"}
    continuation_id = supplied["metadata"]["continuation_assignment_id"]
    assert (team_dir / "inbox" / f"{continuation_id}.md").exists()
    supplied_again = resolve_user_request.run(
        base_args(
            tmp_path,
            request_id="asn_test:input-required",
            response_json='{"target":"staging"}',
            status="supplied",
            no_continuation=False,
            continuation_assignment_id=None,
        )
    )
    assert supplied_again["metadata"]["continuation_assignment_id"] == continuation_id
    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        resumes = conn.execute("SELECT * FROM assignment_resumes WHERE request_id = ?", ("asn_test:input-required",)).fetchall()
    assert len(resumes) == 1

    supplied_requests = query_user_requests.run(base_args(tmp_path, status="resuming", team=None, assignment_id=None, json=True))
    assert supplied_requests["count"] == 1
    assert supplied_requests["requests"][0]["request_id"] == "asn_test:input-required"

    sunset_result = asyncio.run(
        sunset_team.run(base_args(tmp_path, team="dev", dry_run=True, no_archive=False))
    )
    assert "teams_dev_" in sunset_result["archive"]

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        handle = conn.execute("SELECT status FROM substrate_handles WHERE team_name = 'dev'").fetchone()
    assert handle["status"] == "archived"


def test_execution_board_dispatch_sync_and_block(tmp_path: Path):
    asyncio.run(
        spawn_team.run(
            base_args(
                tmp_path,
                name="dev",
                template="single-agent",
                substrate="external",
                dry_run=True,
                agent_card_url="http://team.example/.well-known/agent-card.json",
                push_url="https://boss.example/a2a/push",
                brief="Patch files.",
                criteria="Return verification.",
                timeout_seconds=30,
            )
        )
    )

    created = execution_board.run(
        base_args(
            tmp_path,
            command="create",
            ticket_id="tkt-ship",
            goal_id="goal-1",
            parent_ticket_id=None,
            title="Ship page",
            mode="patch",
            team="dev",
            priority=10,
            order_id="goal-1",
            body="Edit the landing page.",
            file=None,
            write_scope=["website/content/product/index.md"],
            acceptance=["page exists"],
            verification=["build passes"],
            blocker=[],
            metadata=None,
            json=True,
        )
    )
    assert created["ticket"]["status"] == "ready"

    ticked = execution_board.run(base_args(tmp_path, command="tick", limit=5, json=True))
    assert ticked["dispatched"][0]["assignment_id"] == "tkt-ship-patch"
    board = query_work_board.run(base_args(tmp_path, team=None, json=True))
    assert board["execution_ticket_counts"]["running"] == 1

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        conn.execute("UPDATE team_assignments SET status = 'completed' WHERE assignment_id = 'tkt-ship-patch'")
    synced = execution_board.run(base_args(tmp_path, command="sync", json=True))
    assert synced["synced"][0]["status"] == "completed"
    listed = execution_board.run(base_args(tmp_path, command="list", status="completed", team=None, goal_id=None, json=True))
    assert listed["tickets"][0]["ticket_id"] == "tkt-ship"

    blocked = execution_board.run(
        base_args(
            tmp_path,
            command="create",
            ticket_id="tkt-approval",
            goal_id="goal-1",
            parent_ticket_id=None,
            title="Approve send",
            mode="escalate",
            team="dev",
            priority=20,
            order_id="goal-1",
            body="Approve outbound batch.",
            file=None,
            write_scope=[],
            acceptance=["approved"],
            verification=[],
            blocker=["approval"],
            metadata=None,
            json=True,
        )
    )
    assert blocked["ticket"]["mode"] == "escalate"
    ticked = execution_board.run(base_args(tmp_path, command="tick", limit=5, json=True))
    assert ticked["escalated"][0]["request_id"] == "tkt-approval:approval"
    requests = query_user_requests.run(base_args(tmp_path, status="open", team=None, assignment_id=None, json=True))
    assert requests["requests"][0]["metadata"]["ticket_id"] == "tkt-approval"


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


def test_orchestrator_marks_stale_assignment_and_retry_due(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id="stale-1",
            team_name="dev",
            status="working",
            inbox_path=str(factory / "teams" / "dev" / "inbox" / "stale-1.md"),
            a2a_task_id="task-stale",
        )
        conn.execute(
            "UPDATE team_assignments SET last_heartbeat_at = '2026-05-05 10:00:00' WHERE assignment_id = 'stale-1'"
        )
        db.upsert_assignment(
            conn,
            assignment_id="retry-1",
            team_name="dev",
            status="retrying",
            inbox_path=str(factory / "teams" / "dev" / "inbox" / "retry-1.md"),
        )
        conn.execute(
            """
            UPDATE team_assignments
            SET retry_count = 1, next_retry_at = '2000-01-01 00:00:00'
            WHERE assignment_id = 'retry-1'
            """
        )

    result = orchestrator.run_once(
        base_args(tmp_path, holder="test-orchestrator", stale_minutes=1, lease_ttl_seconds=30, json=True)
    )

    assert {action["action"] for action in result["actions"]} == {"assignment-stale", "retry-due"}
    digest = query_remote_teams.run(base_args(tmp_path, team=None, stale_minutes=5, json=True))
    assignments = {row["assignment_id"]: row for row in digest["assignments"]}
    assert assignments["stale-1"]["status"] == "stale"
    assert "retry-1" not in assignments
    alerts = query_alerts.run(base_args(tmp_path, status="open", severity=None, kind=None, json=True))
    assert alerts["count"] == 1
    assert alerts["alerts"][0]["kind"] == "assignment-stale"
    acked = ack_alert.run(base_args(tmp_path, alert_id=alerts["alerts"][0]["alert_id"]))
    assert acked["status"] == "acknowledged"
    assert query_alerts.run(base_args(tmp_path, status="open", severity=None, kind=None, json=True))["count"] == 0


def test_orchestrator_does_not_mark_waiting_on_user_as_stale(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id="blocked-1",
            team_name="dev",
            status="working",
            inbox_path=str(factory / "teams" / "dev" / "inbox" / "blocked-1.md"),
            a2a_task_id="task-blocked",
        )
        conn.execute(
            "UPDATE team_assignments SET last_heartbeat_at = '2026-05-05 10:00:00' WHERE assignment_id = 'blocked-1'"
        )
        db.upsert_approval_request(
            conn,
            request_id="blocked-1:input-required",
            assignment_id="blocked-1",
            team_name="dev",
            task_id="task-blocked",
            kind="input-required",
            title="Need target",
            prompt="Which target?",
        )

    result = orchestrator.run_once(
        base_args(tmp_path, holder="test-orchestrator", stale_minutes=1, lease_ttl_seconds=30, json=True)
    )

    assert result["actions"] == [
        {
            "action": "waiting-on-user",
            "assignment_id": "blocked-1",
            "team_name": "dev",
            "request_id": "blocked-1:input-required",
        }
    ]
    with db.session(db_path) as conn:
        row = conn.execute("SELECT status, blocked_by FROM team_assignments WHERE assignment_id = 'blocked-1'").fetchone()
    assert row["status"] == "input-required"
    assert row["blocked_by"] == "blocked-1:input-required"


def test_orchestrator_keeps_blocked_sandbox_until_ttl_then_archives(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    team_dir = factory / "teams" / "dev"
    (team_dir / "inbox").mkdir(parents=True)
    (team_dir / "workspace.txt").write_text("important state\n", encoding="utf-8")
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    handle = SubstrateHandle(
        team_name="dev",
        substrate="e2b",
        handle="dry-run-e2b://blocked-1",
        metadata={"dry_run": True, "workspace_path": str(team_dir)},
    )
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id="blocked-1",
            team_name="dev",
            status="input-required",
            inbox_path=str(team_dir / "inbox" / "blocked-1.md"),
            a2a_task_id="task-blocked",
        )
        db.save_assignment_sandbox(
            conn,
            assignment_id="blocked-1",
            team_name="dev",
            handle=handle,
            agent_card_url="http://sandbox.example/card.json",
            status="booted",
            metadata={"dry_run": True},
        )

    first = orchestrator.run_once(
        base_args(
            tmp_path,
            holder="test-orchestrator",
            stale_minutes=1,
            user_request_alert_minutes=9999,
            blocked_sandbox_ttl_minutes=60,
            orphan_sandbox_ttl_minutes=60,
            lease_ttl_seconds=30,
            env=None,
            json=True,
        )
    )
    assert any(action["action"] == "sandbox-blocked" for action in first["actions"])
    with db.session(db_path) as conn:
        row = conn.execute("SELECT status, blocked_since, expires_at FROM assignment_sandboxes WHERE assignment_id = 'blocked-1'").fetchone()
    assert row["status"] == "blocked"
    assert row["blocked_since"] is not None
    assert row["expires_at"] is not None

    with db.session(db_path) as conn:
        conn.execute("UPDATE assignment_sandboxes SET expires_at = '2000-01-01 00:00:00' WHERE assignment_id = 'blocked-1'")

    second = orchestrator.run_once(
        base_args(
            tmp_path,
            holder="test-orchestrator",
            stale_minutes=1,
            user_request_alert_minutes=9999,
            blocked_sandbox_ttl_minutes=60,
            orphan_sandbox_ttl_minutes=60,
            lease_ttl_seconds=30,
            env=None,
            json=True,
        )
    )
    archive_action = next(action for action in second["actions"] if action["action"] == "sandbox-paused-archived")
    with db.session(db_path) as conn:
        row = conn.execute("SELECT status, archive_path, restore_source FROM assignment_sandboxes WHERE assignment_id = 'blocked-1'").fetchone()
    assert row["status"] == "paused_archived"
    assert row["archive_path"] == archive_action["archive_path"]
    assert row["restore_source"] == archive_action["archive_path"]
    assert (Path(row["archive_path"]) / "workspace.txt").read_text(encoding="utf-8") == "important state\n"


def test_orchestrator_archives_orphaned_sandbox(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    team_dir = factory / "teams" / "dev"
    team_dir.mkdir(parents=True)
    (team_dir / "workspace.txt").write_text("orphan state\n", encoding="utf-8")
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    handle = SubstrateHandle(
        team_name="dev",
        substrate="e2b",
        handle="dry-run-e2b://orphan-1",
        metadata={"dry_run": True, "workspace_path": str(team_dir)},
    )
    with db.session(db_path) as conn:
        db.save_assignment_sandbox(
            conn,
            assignment_id="orphan-1",
            team_name="dev",
            handle=handle,
            agent_card_url="http://sandbox.example/card.json",
            status="booted",
            metadata={"dry_run": True},
        )
        conn.execute("UPDATE assignment_sandboxes SET created_at = '2000-01-01 00:00:00' WHERE assignment_id = 'orphan-1'")

    result = orchestrator.run_once(
        base_args(
            tmp_path,
            holder="test-orchestrator",
            stale_minutes=1,
            user_request_alert_minutes=9999,
            blocked_sandbox_ttl_minutes=60,
            orphan_sandbox_ttl_minutes=1,
            lease_ttl_seconds=30,
            env=None,
            json=True,
        )
    )
    archive_action = next(action for action in result["actions"] if action["action"] == "orphan-sandbox-archived")
    with db.session(db_path) as conn:
        row = conn.execute("SELECT status, archive_path FROM assignment_sandboxes WHERE assignment_id = 'orphan-1'").fetchone()
    assert row["status"] == "archived"
    assert row["archive_path"] == archive_action["archive_path"]
    assert (Path(row["archive_path"]) / "workspace.txt").read_text(encoding="utf-8") == "orphan state\n"


def test_resolving_paused_archived_sandbox_records_restore_source(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    team_dir = factory / "teams" / "dev"
    (team_dir / "inbox").mkdir(parents=True)
    archive_path = factory / "archive" / "assignment_sandboxes" / "dev_parent_blocked"
    archive_path.mkdir(parents=True)
    (archive_path / "state.txt").write_text("preserved\n", encoding="utf-8")
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    handle = SubstrateHandle(
        team_name="dev",
        substrate="e2b",
        handle="dry-run-e2b://parent",
        metadata={"dry_run": True, "workspace_path": str(team_dir)},
    )
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id="parent",
            team_name="dev",
            status="input-required",
            inbox_path=str(team_dir / "inbox" / "parent.md"),
            a2a_task_id="task-parent",
        )
        db.upsert_approval_request(
            conn,
            request_id="parent:input-required",
            assignment_id="parent",
            team_name="dev",
            task_id="task-parent",
            kind="input-required",
            title="Need input",
            prompt="Provide target.",
        )
        db.save_assignment_sandbox(
            conn,
            assignment_id="parent",
            team_name="dev",
            handle=handle,
            agent_card_url="http://sandbox.example/card.json",
            status="paused_archived",
            metadata={"dry_run": True},
        )
        db.mark_assignment_sandbox_paused_archived(
            conn,
            assignment_id="parent",
            archive_path=str(archive_path),
            restore_source=str(archive_path),
        )

    result = resolve_user_request.run(
        base_args(
            tmp_path,
            request_id="parent:input-required",
            response_json='{"target":"prod"}',
            status="supplied",
            no_continuation=False,
            continuation_assignment_id=None,
        )
    )
    continuation_id = result["metadata"]["continuation_assignment_id"]
    queued = json.loads((team_dir / "inbox" / f"{continuation_id}.queued.json").read_text(encoding="utf-8"))
    assert queued["resume_strategy"] == "continuation_assignment_restore_sandbox"
    assert queued["sandbox_restore_source"] == str(archive_path)
    with db.session(db_path) as conn:
        resume = conn.execute("SELECT strategy, metadata FROM assignment_resumes WHERE request_id = ?", ("parent:input-required",)).fetchone()
    assert resume["strategy"] == "continuation_assignment_restore_sandbox"
    assert json.loads(resume["metadata"])["sandbox_restore_source"] == str(archive_path)


def test_run_assignment_sandbox_restores_workspace_from_archive(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    team_dir = factory / "teams" / "dev"
    (team_dir / "inbox").mkdir(parents=True)
    (team_dir / "transport.json").write_text(
        json.dumps(
            {
                "protocol": "a2a",
                "substrate": "e2b",
                "push_url": "https://boss.example/a2a/push",
                "push_token_ref": "env://PUSH_TOKEN",
                "bridge_secret_ref": "env://BRIDGE_SECRET",
            }
        ),
        encoding="utf-8",
    )
    (team_dir / "status.json").write_text(json.dumps({"template": "single-agent-team"}), encoding="utf-8")
    archive_path = factory / "archive" / "assignment_sandboxes" / "dev_parent_blocked"
    archive_path.mkdir(parents=True)
    (archive_path / "restored.txt").write_text("from archive\n", encoding="utf-8")
    assignment_id = "parent-resume"
    (team_dir / "inbox" / f"{assignment_id}.queued.json").write_text(
        json.dumps(
            {
                "assignment_id": assignment_id,
                "sandbox_restore_source": str(archive_path),
                "resume_strategy": "continuation_assignment_restore_sandbox",
            }
        ),
        encoding="utf-8",
    )
    env_path = tmp_path / "bridge.env"
    env_path.write_text("PUSH_TOKEN=push\nBRIDGE_SECRET=secret\nE2B_API_KEY=dry\n", encoding="utf-8")
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)

    result = asyncio.run(
        run_for_assignment(
            factory=factory,
            db_path=db_path,
            team="dev",
            assignment_id=assignment_id,
            dry_run=True,
            env_path=env_path,
        )
    )

    assert (team_dir / "restored.txt").read_text(encoding="utf-8") == "from archive\n"
    with db.session(db_path) as conn:
        sandbox = conn.execute("SELECT status, metadata FROM assignment_sandboxes WHERE assignment_id = ?", (assignment_id,)).fetchone()
        event = conn.execute("SELECT kind, state, metadata FROM team_events WHERE assignment_id = ?", (assignment_id,)).fetchone()
    assert result["assignment_id"] == assignment_id
    assert sandbox["status"] == "restored"
    assert json.loads(sandbox["metadata"])["restore_source"] == str(archive_path)
    assert event["kind"] == "assignment-sandbox-restored"
    assert event["state"] == "restored"


def test_run_soak_writes_report_and_validates_runtime_flow(tmp_path: Path) -> None:
    result = run_soak.run(
        base_args(
            tmp_path,
            name="soak-test",
            duration_hours=24,
            duration_seconds=0,
            interval_seconds=1,
            report=None,
            env=None,
        )
    )

    assert result["status"] == "completed"
    assert result["validations"]
    assert result["validations"][0]["failures"] == []

    report_path = Path(result["report_path"])
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["name"] == "soak-test"

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        archived = conn.execute("SELECT status FROM assignment_sandboxes WHERE assignment_id = 'soak-blocked'").fetchone()
        restored = conn.execute("SELECT status FROM assignment_sandboxes WHERE status = 'restored'").fetchone()
    assert archived["status"] == "paused_archived"
    assert restored["status"] == "restored"


def test_operator_board_requeue_cancel_and_explain_blockers(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    team_dir = factory / "teams" / "dev"
    (team_dir / "inbox").mkdir(parents=True)
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    inbox_path = team_dir / "inbox" / "stale-1.md"
    inbox_path.write_text("# stale\n", encoding="utf-8")
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id="stale-1",
            team_name="dev",
            status="stale",
            inbox_path=str(inbox_path),
        )
        db.upsert_assignment(
            conn,
            assignment_id="running-1",
            team_name="dev",
            status="working",
            inbox_path=str(team_dir / "inbox" / "running-1.md"),
            a2a_task_id="task-running",
        )
        db.upsert_approval_request(
            conn,
            request_id="running-1:auth-required",
            assignment_id="running-1",
            team_name="dev",
            task_id="task-running",
            kind="auth-required",
            title="Need login",
            prompt="Provide login.",
        )

    board = query_work_board.run(base_args(tmp_path, team=None, json=True))
    assert board["counts"]["stale"] == 1
    requeued = requeue_assignment.run(base_args(tmp_path, assignment_id="stale-1", force=False))
    assert requeued["status"] == "queued"
    canceled = cancel_assignment.run(base_args(tmp_path, assignment_id="running-1", reason="test cancel"))
    assert canceled["status"] == "cancel-requested"
    blockers = explain_blockers.run(base_args(tmp_path, team=None, json=True))
    assert blockers["counts"]["user_requests"] == 1
    assert any(row["assignment_id"] == "running-1" for row in blockers["assignments"])


def test_spawn_team_from_blueprint_directory(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    blueprint = factory / "team_blueprints" / "research"
    blueprint.mkdir(parents=True)
    (blueprint / "blueprint.yaml").write_text(
        "name: research\nsubstrate: e2b\ntemplate: multi-agent-team\n",
        encoding="utf-8",
    )
    (blueprint / "brief.md").write_text("# Research Brief\n\nGather sourced market context.\n", encoding="utf-8")
    (blueprint / "TEAM_SOUL.md").write_text("# Research Soul\n\nRun on E2B.\n", encoding="utf-8")
    (blueprint / "criteria.md").write_text("# Criteria\n\nReport sourced findings.\n", encoding="utf-8")
    (blueprint / "AGENTS.md").write_text("# Agents\n\nUse A2A.\n", encoding="utf-8")

    parsed = spawn_team.build_parser().parse_args(
        [
            "--factory",
            str(factory),
            "--db",
            str(tmp_path / "harness.sqlite3"),
            "research",
            "--substrate",
            "external",
            "--dry-run",
            "--agent-card-url",
            "http://team.example/.well-known/agent-card.json",
            "--blueprint",
            "research",
            "--template",
            "multi-agent",
        ]
    )
    assert parsed.blueprint == "research"

    result = asyncio.run(spawn_team.run(parsed))

    team_dir = Path(result["path"])
    assert (team_dir / "context" / "hiring_blueprint.md").exists()
    assert "Gather sourced market context" in (team_dir / "brief.md").read_text(encoding="utf-8")
    assert "Run on E2B" in (team_dir / "TEAM_SOUL.md").read_text(encoding="utf-8")
    status = json.loads((team_dir / "status.json").read_text(encoding="utf-8"))
    assert status["template"] == "multi-agent-team"
    assert status["blueprint"] == "research"
    transport = json.loads((team_dir / "transport.json").read_text(encoding="utf-8"))
    assert transport["protocol"] == "a2a"
    assert transport["substrate"] == "external"
    assert transport["blueprint"] == "research"
    assert transport["substrate_handle_ref"] == "sqlite://substrate_handles/research"

    with db.session(Path(tmp_path / "harness.sqlite3")) as conn:
        row = conn.execute("SELECT metadata FROM team_events WHERE team_name = 'research'").fetchone()
    metadata = json.loads(row["metadata"])
    assert metadata["template"] == "multi-agent-team"
    assert metadata["blueprint"] == "research"


def test_control_cli_observes_logs_and_approves_requests(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    team_dir = factory / "teams" / "ops"
    (team_dir / "inbox").mkdir(parents=True)
    (team_dir / "journal.md").write_text("# Journal\n\n- started\n", encoding="utf-8")
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    inbox_path = team_dir / "inbox" / "asn-control.md"
    inbox_path.write_text("# Control assignment\n", encoding="utf-8")
    with db.session(db_path) as conn:
        db.save_substrate_handle(
            conn,
            SubstrateHandle(team_name="ops", substrate="external", handle="http://ops.example/a2a"),
            status="booted",
        )
        db.upsert_assignment(
            conn,
            assignment_id="asn-control",
            team_name="ops",
            status="working",
            inbox_path=str(inbox_path),
            a2a_task_id="task-control",
        )
        db.record_event(
            conn,
            team_name="ops",
            assignment_id="asn-control",
            task_id="task-control",
            source="test",
            kind="working",
            state="working",
        )
        db.upsert_execution_ticket(
            conn,
            ticket_id="tkt-control",
            title="Approve control",
            mode="escalate",
            team_name="ops",
            status="blocked",
            approval_request_id="req-control",
            assignment_id="asn-control",
        )
        db.upsert_approval_request(
            conn,
            request_id="req-control",
            assignment_id="asn-control",
            team_name="ops",
            task_id="task-control",
            kind="approval-required",
            title="Need approval",
            prompt="Approve this.",
        )

    status = control.run(base_args(tmp_path, command="status", team=None, stale_minutes=5, json=True))
    assert status["summary"]["teams"] == 1
    assert status["summary"]["waiting_on_user"] == 1

    logs = control.run(
        base_args(
            tmp_path,
            command="logs",
            team="ops",
            assignment_id="asn-control",
            limit=5,
            tail_lines=10,
            include_files=True,
            json=True,
        )
    )
    assert logs["events"][0]["kind"] == "working"
    assert "started" in logs["journal_tail"]
    assert "Control assignment" in logs["files"]["inbox_path"]

    approved = control.run(
        base_args(
            tmp_path,
            command="requests",
            request_command="approve",
            request_id="req-control",
            comment="approved by test",
            continue_work=False,
            json=True,
        )
    )
    assert approved["request"]["status"] == "supplied"
    assert approved["request"]["response"]["approved"] is True
    assert approved["ticket"]["status"] == "completed"


def test_control_cli_changes_goals_and_lists_resources(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    team_dir = factory / "teams" / "dev"
    team_dir.mkdir(parents=True)
    resource_path = factory / "resources" / "website" / "main.json"
    resource_path.parent.mkdir(parents=True)
    resource_path.write_text(
        json.dumps({"id": "website/main", "title": "Main website", "kind": "website", "state": "ready"}),
        encoding="utf-8",
    )
    db_path = tmp_path / "harness.sqlite3"
    db.init_db(db_path)
    with db.session(db_path) as conn:
        db.upsert_execution_ticket(
            conn,
            ticket_id="tkt-goal",
            title="Goal task",
            mode="patch",
            team_name="dev",
            status="ready",
        )

    changed = control.run(
        base_args(
            tmp_path,
            command="goals",
            goal_command="set",
            ticket_id="tkt-goal",
            goal_id="goal-growth",
            json=True,
        )
    )
    assert changed["ticket"]["goal_id"] == "goal-growth"

    goals = control.run(base_args(tmp_path, command="goals", goal_command="list", json=True))
    assert goals["goals"][0]["goal_id"] == "goal-growth"
    resources = control.run(base_args(tmp_path, command="resources", resource_command="list", json=True))
    assert resources["resources"][0]["id"] == "website/main"
    resource = control.run(
        base_args(tmp_path, command="resources", resource_command="get", resource_id="website/main", json=True)
    )
    assert resource["title"] == "Main website"
