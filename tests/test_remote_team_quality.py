from __future__ import annotations

from hermes_harness.remote_team.quality import enforce_response_quality, validate_response_quality


CAMPAIGN_BODY = """Card type
Campaign cycle

Goal
Run an X campaign.
"""


def test_quality_gate_blocks_lazy_campaign_completion() -> None:
    response = {
        "ok": True,
        "status": "completed",
        "main_card_update": {"action": "complete", "status": "done"},
        "result": {
            "remote_team_protocol": True,
            "mock_x_posts": [{"id": "p1"}],
            "main_card_update": {"action": "complete", "status": "done"},
        },
    }

    gated = enforce_response_quality(response, task_body=CAMPAIGN_BODY)

    assert gated["main_card_update"]["action"] == "block"
    assert gated["main_card_update"]["status"] == "blocked"
    assert gated["result"]["quality_gate"]["ok"] is False
    assert "missing strategy_decisions" in gated["result"]["quality_gate"]["reasons"]


def test_quality_gate_accepts_autonomous_campaign_report() -> None:
    response = {
        "ok": True,
        "status": "completed",
        "main_card_update": {"action": "complete", "status": "done"},
        "result": {
            "remote_team_protocol": True,
            "strategy_decisions": [{"decision": "post daily", "rationale": "keeps signal fresh"}],
            "execution_plan": {"cadence": "daily", "success_thresholds": ["qualified replies"]},
            "execution_ledger": [{"period": "day-1", "status": "done", "posts": [{"id": "p1"}]}],
            "self_review": {"assessment": "adequate", "reason": "all periods covered"},
            "next_adjustment": "test a sharper hook next",
            "mock_x_posts": [{"id": "p1"}],
            "main_card_update": {"action": "complete", "status": "done"},
        },
    }

    gate = validate_response_quality(response, task_body=CAMPAIGN_BODY)

    assert gate.ok is True
    assert gate.reasons == ()


def test_quality_gate_accepts_explicit_blocker_report() -> None:
    response = {
        "ok": True,
        "status": "blocked",
        "main_card_update": {"action": "block", "status": "blocked"},
        "result": {
            "remote_team_protocol": True,
            "blockers": [{"summary": "X credentials are missing"}],
            "main_card_update": {"action": "block", "status": "blocked"},
        },
    }

    gate = validate_response_quality(response, task_body=CAMPAIGN_BODY)

    assert gate.ok is True


def test_quality_gate_blocks_empty_block_action() -> None:
    response = {
        "ok": True,
        "status": "blocked",
        "main_card_update": {"action": "block", "status": "blocked"},
        "result": {
            "remote_team_protocol": True,
            "blockers": [],
            "main_card_update": {"action": "block", "status": "blocked"},
        },
    }

    gate = validate_response_quality(response, task_body=CAMPAIGN_BODY)

    assert gate.ok is False
    assert gate.reasons == ("block action without blockers",)
