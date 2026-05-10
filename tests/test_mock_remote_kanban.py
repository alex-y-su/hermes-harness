import importlib.util
import random
from pathlib import Path
from types import SimpleNamespace


def load_mock_module():
    path = Path(__file__).resolve().parents[1] / "scripts/hermes/mock_remote_kanban.py"
    spec = importlib.util.spec_from_file_location("mock_remote_kanban", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mock_result_matches_kpi_approval_and_maintenance_contract():
    mock = load_mock_module()
    task = SimpleNamespace(
        id="t_contract",
        body="""Stream: maintenance
Goal: Refresh the existing SEO landing page and monitor decaying rankings.
Hypothesis: Updating proof screenshots will recover qualified organic visits.
Approval required: false
Approval reason: Draft and mock execution only; no external publishing.
Expected deliverables:
- refreshed title/meta options
- broken link list
Requested KPIs:
- qualified organic visits
- ranking movement for target keyword
Measurement window: 14 days after refresh
Decision rule: Continue if organic visits improve 10% without CTA regression.
""",
        tenant="support",
    )

    result = mock._build_result(
        task=task,
        team="seo",
        remote_task_id="seo:mock:1",
        status="success",
        rng=random.Random("contract-test"),
    )

    assert result["stream"] == "maintenance"
    assert result["approval"]["required_before_external_action"] is False
    assert result["requested_kpis"] == [
        "qualified organic visits",
        "ranking movement for target keyword",
    ]
    assert result["measurement_window"] == "14 days after refresh"
    assert result["decision_rule"] == (
        "Continue if organic visits improve 10% without CTA regression."
    )
    assert result["reported_kpis"][0]["name"] == "qualified organic visits"
    assert "maintenance_summary" in result
    assert "test_telemetry" in result


def test_mock_parser_accepts_heading_lines_without_colons():
    mock = load_mock_module()
    task = SimpleNamespace(
        id="t_heading_style",
        body="""Stream
Growth

Approval required
Human-approved for public posting. Auto-approved for drafting.

Expected deliverables
1. Thread draft
2. Hook variants

Requested KPIs
Draft quality score; profile clicks; demo clicks

Measurement window
72 hours after posting

Decision rule
Iterate if profile-click rate is >=1.5%.
""",
        tenant="growth",
    )

    result = mock._build_result(
        task=task,
        team="social",
        remote_task_id="social:mock:1",
        status="success",
        rng=random.Random("heading-style-test"),
    )

    assert result["stream"] == "growth"
    assert result["approval"]["tier"] == "human"
    assert result["requested_kpis"] == [
        "Draft quality score",
        "profile clicks",
        "demo clicks",
    ]
    assert result["reported_kpis"][1]["name"] == "profile clicks"
    assert result["measurement_window"] == "72 hours after posting"
    assert result["decision_rule"] == "Iterate if profile-click rate is >=1.5%."
