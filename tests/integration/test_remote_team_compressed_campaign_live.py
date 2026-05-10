from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from hermes_harness.remote_team.transports import call_team


pytestmark = [pytest.mark.integration, pytest.mark.smoke]


def test_live_vm203_compressed_x_campaign_end_to_end(tmp_path: Path) -> None:
    if os.environ.get("HERMES_HUB_COMPRESSED_CAMPAIGN_TEST") != "1":
        pytest.skip("set HERMES_HUB_COMPRESSED_CAMPAIGN_TEST=1 to run the compressed live campaign")
    base_url = (os.environ.get("HERMES_HUB_URL") or "").rstrip("/")
    token = os.environ.get("HERMES_HUB_API_TOKEN")
    if not base_url or not token:
        pytest.skip("HERMES_HUB_URL and HERMES_HUB_API_TOKEN are required")

    tenant_id = os.environ.get("HERMES_HUB_COMPRESSED_TENANT", "xteam_compressed_campaign")
    board = "x-compressed-campaign"
    evidence_dir = Path(os.environ.get("HERMES_HUB_COMPRESSED_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence_dir.mkdir(parents=True, exist_ok=True)

    _hub_delete(base_url, token, f"/v1/tenants/{tenant_id}")
    registry = _write_registry(
        evidence_dir=evidence_dir,
        base_url=base_url,
        tenant_id=tenant_id,
        board=board,
    )
    request = _campaign_request(board=board)
    (evidence_dir / "request.json").write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")

    timeline: list[dict[str, Any]] = []
    try:
        submit = call_team(registry_path=registry, team="x", operation="submit_or_get", request=request, timeout=480)
        _write_json(evidence_dir / "submit-response.json", submit)
        timeline.append(_timeline_entry("submit", submit))

        active_reports = 0
        final: dict[str, Any] | None = None
        for index in range(1, 5):
            should_complete = index >= 3
            status_request = _status_request(
                request,
                board=board,
                remote_task_id=submit.get("remote_task_id"),
                poll_index=index,
                should_complete=should_complete,
            )
            _write_json(evidence_dir / f"status-request-{index}.json", status_request)
            status = call_team(
                registry_path=registry,
                team="x",
                operation="status",
                request=status_request,
                timeout=480,
            )
            _write_json(evidence_dir / f"status-response-{index}.json", status)
            timeline.append(_timeline_entry(f"status-{index}", status))

            action = _main_update(status).get("action")
            if action == "complete":
                final = status
                break
            if action == "keep_running":
                active_reports += 1

        inspection = _inspect_tenant(base_url, token, tenant_id, evidence_dir)
        summary = {
            "tenant_id": tenant_id,
            "board": board,
            "timeline": timeline,
            "active_reports_before_completion": active_reports,
            "final_action": _main_update(final or {}).get("action"),
            "submit_post_count": len(_posts(submit)),
            "final_report_post_count": len(_posts(final or {})),
            "submit_has_autonomy_contract": _has_autonomy_contract(submit),
            "final_has_autonomy_contract": _has_autonomy_contract(final or {}),
            "remote_posts_count_on_disk": inspection.get("posts_count"),
            "remote_post_ids_on_disk": inspection.get("post_ids"),
            "remote_cron_jobs_count_on_disk": inspection.get("cron_jobs_count"),
            "remote_schedule_evidence": inspection.get("schedule_evidence"),
            "inspection": inspection,
        }
        _write_json(evidence_dir / "summary.json", summary)
    finally:
        _hub_post(base_url, token, f"/v1/tenants/{tenant_id}/agent/stop")

    assert submit["ok"] is True, submit
    assert submit["status"] == "completed", submit
    assert len(_posts(submit)) >= 2, submit
    assert active_reports >= 2, timeline
    assert final is not None, timeline
    assert _has_autonomy_contract(submit), submit
    assert _has_autonomy_contract(final), final
    assert _main_update(final).get("action") == "complete", final
    assert _main_update(final).get("status") == "done", final
    assert inspection.get("posts_count", 0) >= 4, inspection
    assert inspection.get("cron_jobs_count", 0) >= 1, inspection


def _write_registry(*, evidence_dir: Path, base_url: str, tenant_id: str, board: str) -> Path:
    registry = evidence_dir / "remote_teams.json"
    registry.write_text(
        json.dumps(
            {
                "remote_teams": {
                    "x": {
                        "transport": "hermes-hub",
                        "base_url": base_url,
                        "api_token_env": "HERMES_HUB_API_TOKEN",
                        "tenant_id": tenant_id,
                        "display_name": "Compressed X campaign verification",
                        "ensure_tenant": True,
                        "idle_timeout_seconds": 300,
                        "board": board,
                        "state_path": str(evidence_dir / "hub-state.json"),
                        "poll_interval_seconds": 2,
                        "product_context": _product_context(),
                        "team_prompt": _x_team_prompt(),
                    }
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return registry


def _campaign_request(*, board: str) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "protocol_version": "1",
        "source_team": "main",
        "target_team": "x",
        "external_id": "main:x-compressed-campaign:card-1",
        "source_board": "main",
        "source_task_id": "card-1",
        "task": {
            "title": "[x][growth] Compressed end-to-end campaign",
            "tenant": "growth",
            "priority": 9,
            "body": f"""Card type
Campaign cycle

Stream
Growth

Goal
Run a complete compressed X campaign for Hermes Harness remote-team orchestration from launch to final report.

Time compression
1 campaign day = 1 minute. This test compresses a multi-day marketing campaign into minutes.

Campaign start at
{now}

Cycle window
3 compressed days / 3 minutes.

Poll interval
15 seconds

Heartbeat schedule
Every 15 seconds while the card remains running.

Posting cadence
At least one X post per compressed day. X transport limits are relaxed for this mock gateway test.

Review cadence
Every compressed day / every 1 minute.

Expected deliverables
1. Initial campaign strategy
2. Initial X posts through the configured gateway
3. Additional X posts during active compressed-day status polls
4. KPI checks during active compressed-day status polls
5. Final KPI summary and completed main-card update at the campaign end

Requested KPIs
Qualified replies; Profile clicks; Demo clicks

Measurement window
The full 3-minute compressed campaign.

Approval required
Auto-approved for this mock X gateway test only.

Continue rule
Keep running before the final poll while the compressed campaign is active.

Stop rule
On a status poll where poll.campaign_should_complete=true, stop posting and return main_card_update.action='complete' and main_card_update.status='done'.

Definition of done
The campaign has produced posts on at least two active compressed days, checked KPIs, retained an executable heartbeat schedule, and returned a final completion report.

Reporting format
Return only JSON using the requested remote-team protocol response schema.
""",
        },
    }


def _status_request(
    request: dict[str, Any],
    *,
    board: str,
    remote_task_id: object,
    poll_index: int,
    should_complete: bool,
) -> dict[str, Any]:
    current_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "protocol_version": "1",
        "source_team": "main",
        "target_team": "x",
        "external_id": request["external_id"],
        "source_board": request["source_board"],
        "source_task_id": request["source_task_id"],
        "remote_task_id": remote_task_id,
        "board": board,
        "force_report": True,
        "poll": {
            "force_report": True,
            "owner": "main-dashboard",
            "current_time": current_time,
            "compressed_day_index": poll_index,
            "campaign_should_complete": should_complete,
            "interval_seconds": 15,
            "reason": "compressed campaign heartbeat",
            "main_card_status": "running",
        },
        "task": request["task"],
    }


def _product_context() -> str:
    return (
        "Hermes Harness orchestrates Hermes AI agents through Kanban. The main team delegates "
        "high-level work to hosted sub-teams. This verification compresses a real multi-day X "
        "campaign into minutes while preserving strategy, posting, KPI checks, maintenance, "
        "and final reporting semantics."
    )


def _x_team_prompt() -> str:
    return (
        "You are the Social Media X sub-team. Treat $HERMES_HOME/mock-x/posts.jsonl as the real X API "
        "for this environment. X rate limits are relaxed for this compressed test: posting every "
        "compressed day/minute is allowed. On submit_or_get, create the strategy, append at least two "
        "mock-X post receipts, create KPI and maintenance internal work, and create an executable "
        "heartbeat schedule in $HERMES_HOME/cron/jobs.json every 15 seconds while the campaign is active. "
        "On each status poll, trust poll.current_time, poll.compressed_day_index, and "
        "poll.campaign_should_complete from the request. If campaign_should_complete=false, append one "
        "new X post for that compressed day, check/report KPIs, and keep main_card_update.action='keep_running'. "
        "If campaign_should_complete=true, do not create more posts; produce a final KPI/campaign summary and "
        "set main_card_update.action='complete' and main_card_update.status='done'."
    )


def _inspect_tenant(base_url: str, token: str, tenant_id: str, evidence_dir: Path) -> dict[str, Any]:
    prompt = (
        "Read-only inspection. Do not create, edit, append, delete, schedule, or post anything. "
        "Inspect $HERMES_HOME/mock-x/posts.jsonl and $HERMES_HOME/cron/jobs.json. Return only JSON "
        "with keys posts_count, post_ids, posts_path, cron_jobs_count, cron_jobs, schedule_evidence, explanation."
    )
    run = _hub_json(
        base_url,
        token,
        "POST",
        f"/v1/tenants/{tenant_id}/runs",
        {"input": prompt, "session_id": "compressed-campaign-readonly-inspect", "model": "hermes-agent"},
    )
    _write_json(evidence_dir / "readonly-inspect-start.json", run)
    run_id = run.get("run_id") or run.get("id")
    status = run
    for _ in range(90):
        if status.get("status") in {"completed", "failed", "cancelled", "canceled"}:
            break
        time.sleep(2)
        status = _hub_json(base_url, token, "GET", f"/v1/tenants/{tenant_id}/runs/{run_id}", None)
    _write_json(evidence_dir / "readonly-inspect-status.json", status)
    try:
        parsed = json.loads(status.get("output") or "{}")
    except json.JSONDecodeError:
        parsed = {"raw_output": status.get("output")}
    return parsed if isinstance(parsed, dict) else {"raw_output": parsed}


def _timeline_entry(label: str, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "ok": response.get("ok"),
        "status": response.get("status"),
        "remote_task_id": response.get("remote_task_id"),
        "hub_job_id": (response.get("hub") or {}).get("job_id"),
        "main_card_update": _main_update(response),
        "post_count": len(_posts(response)),
    }


def _main_update(response: dict[str, Any]) -> dict[str, Any]:
    update = response.get("main_card_update")
    if isinstance(update, dict):
        return update
    result = response.get("result")
    if isinstance(result, dict) and isinstance(result.get("main_card_update"), dict):
        return result["main_card_update"]
    return {}


def _posts(response: dict[str, Any]) -> list[dict[str, Any]]:
    result = response.get("result")
    if not isinstance(result, dict):
        return []
    posts = result.get("mock_x_posts")
    return posts if isinstance(posts, list) else []


def _has_autonomy_contract(response: dict[str, Any]) -> bool:
    result = response.get("result")
    if not isinstance(result, dict):
        return False
    return all(
        bool(result.get(key))
        for key in ("strategy_decisions", "execution_plan", "execution_ledger", "self_review")
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _hub_json(base_url: str, token: str, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers={
            "authorization": "Bearer " + token,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    raw = urllib.request.urlopen(request, timeout=30).read().decode("utf-8")
    parsed = json.loads(raw) if raw.strip() else {}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _hub_post(base_url: str, token: str, path: str) -> None:
    try:
        _hub_json(base_url, token, "POST", path, {})
    except Exception:
        return


def _hub_delete(base_url: str, token: str, path: str) -> None:
    request = urllib.request.Request(
        base_url + path,
        data=b"",
        method="DELETE",
        headers={"authorization": "Bearer " + token},
    )
    try:
        urllib.request.urlopen(request, timeout=30).read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
