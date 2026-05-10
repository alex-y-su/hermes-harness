from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from harness import db
from harness.factory import append_journal, utc_now, write_json
from harness.models import SubstrateHandle
from harness.tools import orchestrator, query_alerts, query_work_board, resolve_user_request
from harness.tools.common import add_factory_args, paths
from harness.tools.run_assignment_sandbox import run_for_assignment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a supervised 24/7 soak scenario and write a JSON report.")
    add_factory_args(parser)
    parser.add_argument("--name", default=None)
    parser.add_argument("--duration-hours", type=float, default=24.0)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--report", default=None)
    parser.add_argument("--env", default=os.getenv("HARNESS_ENV_PATH"))
    return parser


def _ts() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _namespace(args: argparse.Namespace, **overrides: Any) -> argparse.Namespace:
    data = vars(args).copy()
    data.update(overrides)
    return argparse.Namespace(**data)


def _team_setup(factory: Path, db_path: Path, name: str) -> Path:
    team_dir = factory / "teams" / name
    (team_dir / "inbox").mkdir(parents=True, exist_ok=True)
    (team_dir / "outbox").mkdir(exist_ok=True)
    (team_dir / "workspace.txt").write_text("initial soak workspace state\n", encoding="utf-8")
    write_json(
        team_dir / "status.json",
        {
            "team_name": name,
            "state": "soak-running",
            "template": "single-agent-team",
            "substrate": "e2b",
            "updated_at": utc_now(),
            "dry_run": True,
        },
    )
    write_json(
        team_dir / "transport.json",
        {
            "protocol": "a2a",
            "substrate": "e2b",
            "per_assignment": True,
            "agent_card_url": "",
            "push_url": "http://127.0.0.1:8787/a2a/push",
            "team_bearer_token_ref": "env://SOAK_TEAM_BEARER",
            "push_token_ref": "env://SOAK_PUSH_TOKEN",
            "bridge_secret_ref": "env://SOAK_BRIDGE_SECRET",
        },
    )
    (team_dir / "brief.md").write_text("24/7 soak dry-run team.\n", encoding="utf-8")
    (team_dir / "criteria.md").write_text("Exercise blockers, retries, alerts, sandbox archive, and restore.\n", encoding="utf-8")
    append_journal(team_dir / "journal.md", "started 24/7 soak dry-run scenario")
    handle = SubstrateHandle(
        team_name=name,
        substrate="e2b",
        handle=f"dry-run-e2b://{name}",
        metadata={"dry_run": True, "workspace_path": str(team_dir), "per_assignment": True},
    )
    with db.session(db_path) as conn:
        db.save_substrate_handle(conn, handle, status="booted")
        db.record_event(
            conn,
            team_name=name,
            source="harness.run_soak",
            kind="soak-started",
            state="running",
            metadata={"dry_run": True},
        )
    return team_dir


def _seed_retry(factory: Path, db_path: Path, team_name: str) -> str:
    assignment_id = "soak-retry"
    inbox_path = factory / "teams" / team_name / "inbox" / f"{assignment_id}.md"
    inbox_path.write_text("# Retry assignment\n\nThis assignment starts retrying and should become queued.\n", encoding="utf-8")
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id=assignment_id,
            team_name=team_name,
            status="retrying",
            inbox_path=str(inbox_path),
        )
        conn.execute(
            """
            UPDATE team_assignments
            SET retry_count = 1,
                next_retry_at = '2000-01-01 00:00:00',
                status_reason = 'soak forced retry'
            WHERE assignment_id = ?
            """,
            (assignment_id,),
        )
    return assignment_id


def _seed_blocked_sandbox(factory: Path, db_path: Path, team_name: str) -> str:
    assignment_id = "soak-blocked"
    team_dir = factory / "teams" / team_name
    inbox_path = team_dir / "inbox" / f"{assignment_id}.md"
    inbox_path.write_text("# Blocked assignment\n\nThis assignment waits on user input.\n", encoding="utf-8")
    handle = SubstrateHandle(
        team_name=team_name,
        substrate="e2b",
        handle=f"dry-run-e2b://{assignment_id}",
        metadata={"dry_run": True, "workspace_path": str(team_dir)},
    )
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id=assignment_id,
            team_name=team_name,
            status="input-required",
            inbox_path=str(inbox_path),
            a2a_task_id=f"task-{assignment_id}",
        )
        db.upsert_approval_request(
            conn,
            request_id=f"{assignment_id}:input-required",
            assignment_id=assignment_id,
            team_name=team_name,
            task_id=f"task-{assignment_id}",
            kind="input-required",
            title="Soak target required",
            prompt="Provide the target environment.",
            required_fields=[{"name": "target", "type": "string"}],
            metadata={"source": "run_soak"},
        )
        conn.execute(
            "UPDATE approval_requests SET created_at = '2000-01-01 00:00:00' WHERE request_id = ?",
            (f"{assignment_id}:input-required",),
        )
        db.save_assignment_sandbox(
            conn,
            assignment_id=assignment_id,
            team_name=team_name,
            handle=handle,
            agent_card_url="http://sandbox.example/.well-known/agent-card.json",
            status="booted",
            metadata={"dry_run": True},
        )
    return assignment_id


def _seed_stale(factory: Path, db_path: Path, team_name: str) -> str:
    assignment_id = "soak-stale"
    inbox_path = factory / "teams" / team_name / "inbox" / f"{assignment_id}.md"
    inbox_path.write_text("# Stale assignment\n\nThis assignment should become stale and alert once.\n", encoding="utf-8")
    with db.session(db_path) as conn:
        db.upsert_assignment(
            conn,
            assignment_id=assignment_id,
            team_name=team_name,
            status="working",
            inbox_path=str(inbox_path),
            a2a_task_id=f"task-{assignment_id}",
        )
        conn.execute(
            "UPDATE team_assignments SET last_heartbeat_at = '2000-01-01 00:00:00' WHERE assignment_id = ?",
            (assignment_id,),
        )
    return assignment_id


def _force_blocked_archive(args: argparse.Namespace, *, factory: Path, db_path: Path, blocked_assignment: str) -> None:
    orchestrator.run_once(
        _namespace(
            args,
            blocked_sandbox_ttl_minutes=60,
            orphan_sandbox_ttl_minutes=60,
            stale_minutes=1,
            user_request_alert_minutes=0,
            lease_ttl_seconds=30,
            json=True,
        )
    )
    with db.session(db_path) as conn:
        conn.execute(
            "UPDATE assignment_sandboxes SET expires_at = '2000-01-01 00:00:00' WHERE assignment_id = ?",
            (blocked_assignment,),
        )
    orchestrator.run_once(
        _namespace(
            args,
            blocked_sandbox_ttl_minutes=60,
            orphan_sandbox_ttl_minutes=60,
            stale_minutes=1,
            user_request_alert_minutes=0,
            lease_ttl_seconds=30,
            json=True,
        )
    )


def _resolve_and_restore(args: argparse.Namespace, *, factory: Path, db_path: Path, team_name: str, blocked_assignment: str) -> str:
    request_id = f"{blocked_assignment}:input-required"
    resolved = resolve_user_request.run(
        _namespace(
            args,
            request_id=request_id,
            response_json='{"target":"soak"}',
            status="supplied",
            no_continuation=False,
            continuation_assignment_id=None,
        )
    )
    continuation_id = resolved["metadata"]["continuation_assignment_id"]
    env_path = factory / "reports" / f"{team_name}.soak.env"
    env_path.write_text("SOAK_PUSH_TOKEN=push\nSOAK_BRIDGE_SECRET=secret\nE2B_API_KEY=dry\n", encoding="utf-8")
    asyncio.run(
        run_for_assignment(
            factory=factory,
            db_path=db_path,
            team=team_name,
            assignment_id=continuation_id,
            dry_run=True,
            env_path=env_path,
        )
    )
    return str(continuation_id)


def _snapshot(args: argparse.Namespace) -> dict[str, Any]:
    board = query_work_board.run(_namespace(args, team=None, json=True))
    alerts = query_alerts.run(_namespace(args, status="open", severity=None, kind=None, json=True))
    return {
        "ts": _ts(),
        "counts": board["counts"],
        "alerts": alerts["count"],
        "sandboxes": [
            {
                "assignment_id": row["assignment_id"],
                "team_name": row["team_name"],
                "status": row["status"],
                "archive_path": row["archive_path"],
                "restore_source": row["restore_source"],
            }
            for row in board.get("sandboxes", [])
        ],
    }


def _validate(db_path: Path, *, blocked_assignment: str, continuation_id: str, retry_assignment: str, stale_assignment: str) -> list[str]:
    failures: list[str] = []
    with db.session(db_path) as conn:
        blocked = conn.execute("SELECT status, archive_path, restore_source FROM assignment_sandboxes WHERE assignment_id = ?", (blocked_assignment,)).fetchone()
        continuation = conn.execute("SELECT status, metadata FROM assignment_sandboxes WHERE assignment_id = ?", (continuation_id,)).fetchone()
        retry = conn.execute("SELECT status FROM team_assignments WHERE assignment_id = ?", (retry_assignment,)).fetchone()
        stale = conn.execute("SELECT status FROM team_assignments WHERE assignment_id = ?", (stale_assignment,)).fetchone()
        stale_alerts = conn.execute("SELECT COUNT(*) AS count FROM operator_alerts WHERE kind = 'assignment-stale' AND assignment_id = ?", (stale_assignment,)).fetchone()
    if not blocked or blocked["status"] != "paused_archived" or not blocked["restore_source"]:
        failures.append("blocked sandbox was not paused_archived with restore_source")
    if not continuation or continuation["status"] != "restored":
        failures.append("continuation sandbox was not restored")
    elif not json.loads(continuation["metadata"] or "{}").get("restore_source"):
        failures.append("continuation sandbox metadata lacks restore_source")
    if not retry or retry["status"] != "queued":
        failures.append("retry assignment did not become queued")
    if not stale or stale["status"] != "stale":
        failures.append("stale assignment did not become stale")
    if int(stale_alerts["count"] or 0) != 1:
        failures.append("stale alert was not created exactly once")
    return failures


def run(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    name = args.name or f"soak-{_stamp().lower()}"
    duration_seconds = float(args.duration_seconds) if args.duration_seconds is not None else float(args.duration_hours) * 3600
    interval_seconds = max(1.0, float(args.interval_seconds))
    report_path = Path(args.report) if args.report else factory / "reports" / f"soak-{name}.json"
    start = datetime.now(UTC)
    end = start + timedelta(seconds=duration_seconds)
    report: dict[str, Any] = {
        "name": name,
        "status": "running",
        "pid": os.getpid(),
        "started_at": _ts(),
        "expected_end_at": end.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "report_path": str(report_path),
        "checkpoints": [],
        "validations": [],
    }
    _write_report(report_path, report)

    try:
        _team_setup(factory, db_path, name)
        retry_assignment = _seed_retry(factory, db_path, name)
        blocked_assignment = _seed_blocked_sandbox(factory, db_path, name)
        stale_assignment = _seed_stale(factory, db_path, name)
        _force_blocked_archive(args, factory=factory, db_path=db_path, blocked_assignment=blocked_assignment)
        continuation_id = _resolve_and_restore(
            args,
            factory=factory,
            db_path=db_path,
            team_name=name,
            blocked_assignment=blocked_assignment,
        )
        failures = _validate(
            db_path,
            blocked_assignment=blocked_assignment,
            continuation_id=continuation_id,
            retry_assignment=retry_assignment,
            stale_assignment=stale_assignment,
        )
        report["validations"].append({"ts": _ts(), "failures": failures})
        if failures:
            report["status"] = "failed"
            _write_report(report_path, report)
            return report

        while datetime.now(UTC) < end:
            orchestrator.run_once(
                _namespace(
                    args,
                    blocked_sandbox_ttl_minutes=60,
                    orphan_sandbox_ttl_minutes=60,
                    stale_minutes=1,
                    user_request_alert_minutes=60,
                    lease_ttl_seconds=30,
                    json=True,
                )
            )
            report["checkpoints"].append(_snapshot(args))
            report["last_checkpoint_at"] = report["checkpoints"][-1]["ts"]
            _write_report(report_path, report)
            time.sleep(min(interval_seconds, max(0.0, (end - datetime.now(UTC)).total_seconds())))

        report["status"] = "completed"
        report["completed_at"] = _ts()
        report["checkpoints"].append(_snapshot(args))
        _write_report(report_path, report)
        return report
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        report["failed_at"] = _ts()
        _write_report(report_path, report)
        raise


def main(argv: list[str] | None = None) -> None:
    result = run(build_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
