from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from hermes_harness.remote_team import poller
from hermes_harness.remote_team.poller import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    poll_decision,
    _parse_interval,
    _remote_context,
    _status_request,
)


def test_poll_decision_uses_card_poll_interval() -> None:
    task = SimpleNamespace(
        id="t1",
        title="Campaign",
        body="Poll interval: 10 minutes",
        status="running",
        started_at=None,
        created_at=None,
    )
    result = {
        "remote_team_protocol_response": {
            "remote_task_id": "remote-1",
            "updated_at": "2026-05-10T11:40:00Z",
        }
    }
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc).timestamp()

    decision = poll_decision(task, result, {}, now=now)

    assert decision.due is True
    assert decision.interval_seconds == 10 * 60
    assert decision.next_due_at == "2026-05-10T11:50:00Z"


def test_poll_decision_honors_future_next_report_due_at() -> None:
    task = SimpleNamespace(
        id="t1",
        body="Poll interval: 1 minute\nNext report due at: 2026-05-10T13:00:00Z",
        started_at=None,
        created_at=None,
    )
    result = {}
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc).timestamp()

    decision = poll_decision(task, result, {}, now=now)

    assert decision.due is False
    assert decision.next_due_at == "2026-05-10T13:00:00Z"


def test_interval_parser_clamps_and_understands_cadence_text() -> None:
    assert _parse_interval("5 seconds") == 15
    assert _parse_interval("15 seconds") == 15
    assert _parse_interval("every 2 hours") == 2 * 60 * 60
    assert _parse_interval("daily status report; full review at end") == 24 * 60 * 60
    assert _parse_interval("no clear cadence") is None


def test_status_request_forces_fresh_remote_report() -> None:
    task = SimpleNamespace(
        id="t1",
        title="Campaign",
        body="Review cadence: daily",
        tenant="growth",
        priority="normal",
        status="running",
    )
    remote = _remote_context(
        {
            "remote_team_protocol_response": {
                "external_id": "main:t1",
                "remote_task_id": "remote-1",
                "board": "social",
            }
        }
    )
    decision = poll_decision(task, {}, {}, now=datetime(2026, 5, 10, 12, tzinfo=timezone.utc).timestamp())

    request = _status_request(task, team="social", board="main", remote=remote, decision=decision)

    assert request["force_report"] is True
    assert request["poll"]["owner"] == "main-dashboard"
    assert request["remote_task_id"] == "remote-1"
    assert request["board"] == "social"
    assert request["task"]["body"] == "Review cadence: daily"


def test_default_poll_interval_is_reasonable() -> None:
    task = SimpleNamespace(id="t1", body="", started_at=None, created_at=None)
    now = datetime(2026, 5, 10, 12, tzinfo=timezone.utc).timestamp()

    decision = poll_decision(task, {}, {}, now=now)

    assert decision.interval_seconds == DEFAULT_POLL_INTERVAL_SECONDS
    assert decision.due is False


def test_poll_once_applies_fresh_status_report_to_running_card(tmp_path: Path, monkeypatch) -> None:
    task = SimpleNamespace(
        id="t1",
        title="Campaign",
        body="Poll interval: 10 minutes",
        tenant="growth",
        priority="normal",
        status="running",
        assignee="team:social",
        started_at=None,
        created_at=None,
        claim_lock="claim-1",
        current_run_id=None,
        claim_expires=None,
        result=json.dumps(
            {
                "remote_team_protocol_response": {
                    "external_id": "main:t1",
                    "remote_task_id": "remote-1",
                    "remote_team": "social",
                    "board": "social",
                    "updated_at": "2026-05-10T11:40:00Z",
                }
            }
        ),
    )
    fake_kb = _FakeKanban(tmp_path, [task])
    calls = []

    def fake_call_team(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "protocol_version": "1",
            "external_id": "main:t1",
            "remote_task_id": "remote-1",
            "remote_team": "social",
            "board": "social",
            "status": "completed",
            "updated_at": "2026-05-10T12:00:00Z",
            "main_card_update": {
                "action": "keep_running",
                "status": "running",
                "next_report_due_at": "2026-05-10T13:00:00Z",
            },
            "result": {
                "remote_team_protocol": True,
                "strategy_decisions": [{"decision": "daily KPI cadence", "rationale": "matches campaign goal"}],
                "execution_plan": {"cadence": "daily", "success_thresholds": ["qualified replies"]},
                "execution_ledger": [{"period": "day-1", "status": "active", "posts": []}],
                "self_review": {"assessment": "adequate", "reason": "campaign is collecting signal"},
                "next_adjustment": "increase posting if replies arrive",
                "reports": [{"summary": "KPI collection still in progress"}],
                "main_card_update": {
                    "action": "keep_running",
                    "status": "running",
                    "next_report_due_at": "2026-05-10T13:00:00Z",
                },
            },
        }

    monkeypatch.setattr(poller, "call_team", fake_call_team)

    result = poller.poll_once(
        registry_path=tmp_path / "remote_teams.json",
        board="main",
        kb_module=fake_kb,
        now=datetime(2026, 5, 10, 12, tzinfo=timezone.utc).timestamp(),
    )

    assert result["ok"] is True
    assert result["polled"] == 1
    assert result["updated"] == 1
    assert calls[0]["operation"] == "status"
    assert calls[0]["request"]["force_report"] is True
    assert calls[0]["request"]["remote_task_id"] == "remote-1"
    stored = json.loads(task.result)
    assert stored["remote_team_protocol_response"]["main_card_update"]["action"] == "keep_running"
    assert stored["quality_gate"]["ok"] is True
    assert fake_kb.events[0]["kind"] == "remote_status_report"


def test_poll_once_blocks_lazy_campaign_completion(tmp_path: Path, monkeypatch) -> None:
    task = SimpleNamespace(
        id="t1",
        title="Campaign",
        body="Card type\nCampaign cycle\n\nGoal\nRun an X campaign.",
        tenant="growth",
        priority="normal",
        status="running",
        assignee="team:social",
        started_at=None,
        created_at=None,
        claim_lock="claim-1",
        current_run_id=None,
        claim_expires=None,
        result=json.dumps(
            {
                "remote_team_protocol_response": {
                    "external_id": "main:t1",
                    "remote_task_id": "remote-1",
                    "remote_team": "social",
                    "board": "social",
                    "updated_at": "2026-05-10T11:40:00Z",
                }
            }
        ),
    )
    fake_kb = _FakeKanban(tmp_path, [task])

    def fake_call_team(**kwargs):
        return {
            "ok": True,
            "protocol_version": "1",
            "external_id": "main:t1",
            "remote_task_id": "remote-1",
            "remote_team": "social",
            "board": "social",
            "status": "completed",
            "main_card_update": {"action": "complete", "status": "done"},
            "result": {
                "remote_team_protocol": True,
                "mock_x_posts": [{"id": "p1"}],
                "main_card_update": {"action": "complete", "status": "done"},
            },
        }

    monkeypatch.setattr(poller, "call_team", fake_call_team)

    result = poller.poll_once(
        registry_path=tmp_path / "remote_teams.json",
        board="main",
        kb_module=fake_kb,
        now=datetime(2026, 5, 10, 12, tzinfo=timezone.utc).timestamp(),
    )

    assert result["ok"] is True
    assert fake_kb.blocked[0]["task_id"] == "t1"
    assert "remote_team_quality_gate_failed" in fake_kb.blocked[0]["reason"]


class _FakeKanban:
    def __init__(self, home: Path, tasks: list[SimpleNamespace]) -> None:
        self._home = home
        self._tasks = tasks
        self.events: list[dict[str, object]] = []
        self.heartbeats: list[dict[str, object]] = []
        self.blocked: list[dict[str, object]] = []
        self.comments: list[dict[str, object]] = []

    def connect(self, *, board: str):
        return _FakeConnection(self._tasks)

    def list_tasks(self, conn, status: str):
        return [task for task in self._tasks if task.status == status]

    def kanban_home(self) -> Path:
        return self._home

    def write_txn(self, conn):
        return _FakeTxn()

    def heartbeat_claim(self, conn, task_id: str, *, ttl_seconds: int, claimer: str) -> None:
        self.heartbeats.append({"task_id": task_id, "ttl_seconds": ttl_seconds, "claimer": claimer})

    def _append_event(self, conn, task_id: str, kind: str, payload: dict[str, object], run_id=None) -> None:
        self.events.append({"task_id": task_id, "kind": kind, "payload": payload, "run_id": run_id})

    def block_task(self, conn, task_id: str, *, reason: str) -> bool:
        self.blocked.append({"task_id": task_id, "reason": reason})
        return True

    def add_comment(self, conn, task_id: str, author: str, body: str) -> None:
        self.comments.append({"task_id": task_id, "author": author, "body": body})


class _FakeConnection:
    def __init__(self, tasks: list[SimpleNamespace]) -> None:
        self._tasks = {task.id: task for task in tasks}

    def execute(self, sql: str, params: tuple[object, ...]):
        task_id = str(params[-1])
        task = self._tasks[task_id]
        if "SET result = ?" in sql:
            task.result = params[0]
            task.claim_expires = params[1]
        else:
            task.claim_expires = params[0]
        return SimpleNamespace(rowcount=1)

    def close(self) -> None:
        return None


class _FakeTxn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
