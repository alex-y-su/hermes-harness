from __future__ import annotations

import json
import subprocess
import textwrap
import uuid

import pytest


pytestmark = pytest.mark.integration


def test_remote_kanban_contract_roundtrip(docker_compose_cmd: list[str]) -> None:
    board = f"pytest-contract-{uuid.uuid4().hex[:8]}"
    hermes_home = f"/tmp/hermes-it-{board}"
    script = f"""
set -euo pipefail
rm -rf "{hermes_home}"
mkdir -p "{hermes_home}"

/workspace/scripts/hermes/install-mock-kanban.sh >/tmp/install-mock-kanban.log

grep -q "HERMES_HARNESS_MOCK_REMOTE_KANBAN_START" "$HERMES_INSTALL_DIR/hermes_cli/kanban_db.py"
test -f "$HERMES_INSTALL_DIR/hermes_cli/mock_remote_kanban.py"
hermes version >/tmp/hermes-version.txt || hermes --version >/tmp/hermes-version.txt

hermes kanban boards create "{board}" --switch >/dev/null

growth_body=$(mktemp)
maintenance_body=$(mktemp)
campaign_body=$(mktemp)

cat > "$growth_body" <<'BODY'
Stream
Growth

Goal
Create a public-facing SEO capture page brief for agentic Kanban orchestration.

Hypothesis
A concrete comparison page will produce qualified demo clicks.

Target audience
Technical founders and AI-native operators.

Approval required
Human-approved for public publishing. Auto-approved for drafting.

Approval reason
Publishing the page is an external action; drafting is internal.

Expected deliverables
1. Page brief
2. CTA plan

Requested KPIs
Target-query impressions; Organic CTR; Qualified demo clicks

Measurement window
28 days after approved publication.

Decision rule
Continue if qualified demo clicks are at least 5.

Definition of done
The result preserves requested KPI fields and approval posture.

Reporting format
Return completed deliverables, requested KPIs, reported KPIs, evidence, blockers, next recommendation, measurement window, and decision rule.
BODY

cat > "$maintenance_body" <<'BODY'
Stream
Maintenance

Goal
Audit an existing nurture sequence for broken links and weak activation copy.

Hypothesis
Fixing broken links and weak copy will improve activation.

Target audience
New users who have not created a delegated task.

Approval required
false

Approval reason
Internal audit and mock execution only.

Expected deliverables
1. Broken link list
2. Copy issue list

Requested KPIs
Items kept current; Broken links found; First delegated-task activation rate

Measurement window
Weekly recurring check.

Decision rule
Escalate if any critical link is broken.

Definition of done
The result includes maintenance summary and KPI fields.

Reporting format
Return maintenance summary, requested KPIs, reported KPIs, evidence, blockers, next recommendation, measurement window, and decision rule.
BODY

cat > "$campaign_body" <<'BODY'
Card type
Campaign cycle

Stream
Growth

Goal
Run a social posting strategy for one bounded campaign cycle.

Hypothesis
Receipt-first positioning will create qualified replies.

Target audience
AI builders and founder-operators.

Approval required
Auto-approved for social posting inside standing campaign guardrails.

Expected deliverables
1. Published posts
2. Reply handling
3. KPI status reports

Requested KPIs
Qualified replies; Profile clicks

Measurement window
14 days during active campaign.

Cycle window
2026-05-10..2026-05-24

Review cadence
Daily KPI update, full review every 7 days.

Continue rule
Continue if >=5 qualified replies.

Stop rule
Stop if 10 posts produce 0 qualified replies.

Next report due
2026-05-11T09:00:00Z

Decision rule
Continue if the primary KPI beats the stop rule.

Definition of done
Keep the main card running while the campaign cycle is active.

Reporting format
Return KPI status report, main card update, evidence, blockers, and next recommendation.
BODY

growth_id=$(hermes kanban create "[seo][growth] Pytest Contract Capture Page" \
  --assignee team:seo \
  --tenant growth \
  --body "$(cat "$growth_body")" \
  --json | jq -r .id)

maintenance_id=$(hermes kanban create "[email][maintenance] Pytest Nurture Audit" \
  --assignee team:email \
  --tenant support \
  --body "$(cat "$maintenance_body")" \
  --json | jq -r .id)

campaign_id=$(hermes kanban create "[social][campaign] Pytest Social Cycle" \
  --assignee team:social \
  --tenant growth \
  --body "$(cat "$campaign_body")" \
  --json | jq -r .id)

hermes kanban dispatch --json >/tmp/pytest-contract-dispatch.json
hermes kanban show "$growth_id" --json >/tmp/pytest-growth.json
hermes kanban show "$maintenance_id" --json >/tmp/pytest-maintenance.json
hermes kanban show "$campaign_id" --json >/tmp/pytest-campaign.json

python3 - <<'PY'
import json
from pathlib import Path

growth = json.loads(Path("/tmp/pytest-growth.json").read_text())
maintenance = json.loads(Path("/tmp/pytest-maintenance.json").read_text())
campaign = json.loads(Path("/tmp/pytest-campaign.json").read_text())

def task_result(payload):
    task = payload["task"]
    assert task["status"] == "done", task
    return json.loads(task["result"])

growth_result = task_result(growth)
maintenance_result = task_result(maintenance)

campaign_task = campaign["task"]
assert campaign_task["status"] == "running", campaign_task
campaign_result = json.loads(campaign_task["result"])

assert growth_result["stream"] == "growth", growth_result
assert growth_result["card_type"] == "execution", growth_result
assert growth_result["main_card_update"]["action"] == "complete"
assert growth_result["approval"]["tier"] == "human", growth_result["approval"]
assert growth_result["approval"]["required_before_external_action"] is True
assert growth_result["requested_kpis"] == [
    "Target-query impressions",
    "Organic CTR",
    "Qualified demo clicks",
]
assert [k["name"] for k in growth_result["reported_kpis"]] == growth_result["requested_kpis"]
assert growth_result["measurement_window"] == "28 days after approved publication."
assert growth_result["decision_rule"] == "Continue if qualified demo clicks are at least 5."
assert "growth_summary" in growth_result

assert maintenance_result["stream"] == "maintenance", maintenance_result
assert maintenance_result["card_type"] == "execution", maintenance_result
assert maintenance_result["main_card_update"]["action"] == "complete"
assert maintenance_result["approval"]["tier"] == "automatic", maintenance_result["approval"]
assert maintenance_result["approval"]["required_before_external_action"] is False
assert maintenance_result["requested_kpis"] == [
    "Items kept current",
    "Broken links found",
    "First delegated-task activation rate",
]
assert [k["name"] for k in maintenance_result["reported_kpis"]] == maintenance_result["requested_kpis"]
assert maintenance_result["measurement_window"] == "Weekly recurring check."
assert maintenance_result["decision_rule"] == "Escalate if any critical link is broken."
assert "maintenance_summary" in maintenance_result
assert maintenance_result["maintenance_summary"]["watch_items"]

assert campaign_result["stream"] == "growth", campaign_result
assert campaign_result["card_type"] == "campaign_cycle", campaign_result
assert campaign_result["requested_kpis"] == ["Qualified replies", "Profile clicks"]
assert campaign_result["cycle_window"] == "2026-05-10..2026-05-24"
assert campaign_result["review_cadence"] == "Daily KPI update, full review every 7 days."
assert campaign_result["continue_rule"] == "Continue if >=5 qualified replies."
assert campaign_result["stop_rule"] == "Stop if 10 posts produce 0 qualified replies."
assert campaign_result["next_report_due_at"] == "2026-05-11T09:00:00Z"
assert campaign_result["main_card_update"]["action"] == "keep_running"
assert campaign_result["main_card_update"]["status"] == "running"
assert campaign_result["main_card_update"]["kpi_state"] == "collecting"

for result in (growth_result, maintenance_result, campaign_result):
    for field in (
        "completed_deliverables",
        "requested_kpis",
        "reported_kpis",
        "approval",
        "measurement_window",
        "decision_rule",
        "evidence",
        "next_recommendation",
        "test_telemetry",
    ):
        assert result.get(field), (field, result)
PY

test -f "{hermes_home}/mock-remote-kanban/{board}/seo/board.json"
test -f "{hermes_home}/mock-remote-kanban/{board}/email/board.json"
test -f "{hermes_home}/mock-remote-kanban/{board}/social/board.json"
jq -e ".tasks[\\"$growth_id\\"].result.reported_kpis | length == 3" "{hermes_home}/mock-remote-kanban/{board}/seo/board.json"
jq -e ".tasks[\\"$maintenance_id\\"].result.maintenance_summary.watch_items | length > 0" "{hermes_home}/mock-remote-kanban/{board}/email/board.json"
jq -e ".tasks[\\"$campaign_id\\"].status == \\"running\\"" "{hermes_home}/mock-remote-kanban/{board}/social/board.json"
jq -e ".tasks[\\"$campaign_id\\"].result.main_card_update.action == \\"keep_running\\"" "{hermes_home}/mock-remote-kanban/{board}/social/board.json"
"""

    result = subprocess.run(
        [
            *docker_compose_cmd,
            "run",
            "--rm",
            "-e",
            f"HERMES_HOME={hermes_home}",
            "-e",
            "HERMES_MOCK_KANBAN_SUCCESS_RATE=1",
            "-e",
            "HERMES_MOCK_KANBAN_SEED=pytest-contract",
            "local-vm",
            "bash",
            "-lc",
            textwrap.dedent(script),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout
