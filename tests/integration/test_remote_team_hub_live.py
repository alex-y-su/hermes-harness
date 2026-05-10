from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

from hermes_harness.remote_team.transports import call_team


pytestmark = [pytest.mark.integration, pytest.mark.smoke]


def test_live_vm203_hub_x_remote_team(repo_root: Path, tmp_path: Path) -> None:
    if os.environ.get("HERMES_HUB_LIVE_TEST") != "1":
        pytest.skip("set HERMES_HUB_LIVE_TEST=1 to run the live VM203 Hub test")
    base_url = os.environ.get("HERMES_HUB_URL")
    token = os.environ.get("HERMES_HUB_API_TOKEN")
    if not base_url or not token:
        pytest.skip("HERMES_HUB_URL and HERMES_HUB_API_TOKEN are required")

    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"xteam_{suffix}"
    board = f"x-{suffix}"
    registry = tmp_path / "remote_teams.json"
    registry.write_text(
        json.dumps(
            {
                "remote_teams": {
                    "x": {
                        "transport": "hermes-hub",
                        "base_url": base_url,
                        "api_token_env": "HERMES_HUB_API_TOKEN",
                        "tenant_id": tenant_id,
                        "display_name": "Live X remote team test",
                        "ensure_tenant": True,
                        "board": board,
                        "state_path": str(tmp_path / "hub-state.json"),
                        "poll_interval_seconds": 2,
                        "product_context": _product_context(),
                        "team_prompt": _x_team_prompt(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    request = {
        "protocol_version": "1",
        "source_team": "main",
        "target_team": "x",
        "external_id": f"main:x-live:{suffix}",
        "task": {
            "title": "[x][growth] Live Hub X posting strategy",
            "tenant": "growth",
            "priority": 9,
            "body": _task_body(),
        },
    }

    try:
        response = call_team(registry_path=registry, team="x", operation="submit_or_get", request=request, timeout=360)
        status = call_team(
            registry_path=registry,
            team="x",
            operation="status",
            request={
                "protocol_version": "1",
                "source_team": "main",
                "target_team": "x",
                "external_id": request["external_id"],
            },
            timeout=60,
        )
    finally:
        _hub_post(base_url, token, f"/v1/tenants/{tenant_id}/agent/stop")

    assert response["ok"] is True, response
    assert response["status"] == "completed", response
    assert status["remote_task_id"] == response["remote_task_id"]
    result = response["result"]
    assert result["remote_team_protocol"] is True
    assert result["mock_remote"] is False
    assert len(result["mock_x_posts"]) >= 2
    assert result["main_card_update"]["action"] == "keep_running"
    assert result["main_card_update"]["kpi_state"] == "collecting"
    assert _has_task_matching(result["internal_tasks"], "kpi")
    assert _has_task_matching(result["internal_tasks"], "maintenance") or _has_task_matching(
        result["internal_tasks"], "cadence"
    )
    assert result["maintenance_loop"]["status"] in {"active", "running"}


def _hub_post(base_url: str, token: str, path: str) -> None:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=b"",
        method="POST",
        headers={"authorization": "Bearer " + token},
    )
    try:
        urllib.request.urlopen(request, timeout=30).read()
    except Exception:
        return


def _has_task_matching(tasks: list[dict[str, object]], token: str) -> bool:
    needle = token.lower()
    return any(needle in (str(task.get("title")) + "\n" + str(task.get("body"))).lower() for task in tasks)


def _product_context() -> str:
    return (
        "Hermes Harness is a system for orchestrating Hermes AI agents with Kanban. "
        "The main team delegates high-level business tasks to durable hosted sub-teams. "
        "The X sub-team owns social strategy, posting cadence, KPI checks, and reports back "
        "to the main-team Kanban card."
    )


def _x_team_prompt() -> str:
    return (
        "You are the Social Media X sub-team. Treat the local X gateway journal as the X API. "
        "Before returning, create at least two X posts by appending JSON lines to "
        "$HERMES_HOME/mock-x/posts.jsonl. Each post must have an id beginning with mock-x-, text, "
        "metadata, created_at, and mock_external_api set to x. Create one KPI verification internal "
        "task and one maintenance/cadence internal task in your plan. Return the created post "
        "receipts and internal task records in the JSON response."
    )


def _task_body() -> str:
    next_report = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 24 * 60 * 60))
    return f"""Card type
Campaign cycle

Stream
Growth

Goal
Create and launch a time-boxed X posting strategy for Hermes Harness remote-team orchestration.

Hypothesis
Practical proof posts about main-team to hosted sub-team delegation will generate qualified replies.

Target audience
AI builders and founder-operators.

Approval required
Auto-approved for this mock X gateway test only.

Expected deliverables
1. Seven-day X posting strategy
2. At least two posted X messages through the configured gateway
3. KPI verification task
4. Maintenance/cadence task

Requested KPIs
Qualified replies; Profile clicks; Demo clicks

Measurement window
7 days after posting.

Cycle window
7 days.

Review cadence
Check post metrics daily; report back every 24 hours.

Next report due at
{next_report}

Continue rule
Continue if there is at least 1 qualified reply or 3 profile clicks in the first 48 hours.

Stop rule
Stop if 10 posts produce 0 qualified replies.

Definition of done
Return the strategy, post receipts, KPI plan, maintenance loop, and main-card update.

Reporting format
Return only JSON using the requested remote-team protocol response schema.
"""
