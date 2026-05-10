from __future__ import annotations

from dataclasses import dataclass
from typing import Any


QUALITY_GATE_VERSION = "1"


@dataclass(frozen=True)
class QualityGate:
    ok: bool
    reasons: tuple[str, ...]
    action: str


def enforce_response_quality(response: dict[str, Any], *, task_body: str | None = None) -> dict[str, Any]:
    gate = validate_response_quality(response, task_body=task_body)
    _attach_quality_gate(response, gate)
    if gate.ok:
        return response
    blocked = dict(response)
    result = blocked.get("result") if isinstance(blocked.get("result"), dict) else {}
    result = dict(result)
    result["quality_gate"] = _gate_payload(gate)
    result.setdefault("blockers", [])
    blockers = result["blockers"] if isinstance(result["blockers"], list) else []
    blockers.append(
        {
            "type": "remote_team_quality_gate",
            "severity": "blocked",
            "summary": "Remote team report did not prove autonomous ownership of the delegated work.",
            "reasons": list(gate.reasons),
        }
    )
    result["blockers"] = blockers
    blocked["result"] = result
    blocked["main_card_update"] = {
        **_main_update(response),
        "action": "block",
        "status": "blocked",
        "reason": "remote_team_quality_gate_failed: " + "; ".join(gate.reasons),
    }
    return blocked


def validate_response_quality(response: dict[str, Any], *, task_body: str | None = None) -> QualityGate:
    result = response.get("result")
    if not isinstance(result, dict):
        return QualityGate(ok=True, reasons=(), action="skip_non_object_result")

    main_update = _main_update(response)
    action = str(main_update.get("action") or "")
    if action == "block":
        return _validate_blocker_report(result)
    if action not in {"keep_running", "complete"}:
        return QualityGate(ok=True, reasons=(), action="skip_non_campaign_action")
    if not _is_campaign_like(task_body=task_body, result=result, main_update=main_update):
        return QualityGate(ok=True, reasons=(), action="skip_non_campaign")

    reasons: list[str] = []
    if not _has_meaningful(result.get("strategy_decisions")):
        reasons.append("missing strategy_decisions")
    if not _has_meaningful(result.get("execution_plan")):
        reasons.append("missing execution_plan")
    if not _has_meaningful(result.get("execution_ledger")):
        reasons.append("missing execution_ledger")
    if not _has_meaningful(result.get("self_review")):
        reasons.append("missing self_review")

    if action == "complete":
        if not _has_meaningful(result.get("next_adjustment")) and not _has_meaningful(result.get("next_recommendation")):
            reasons.append("missing next_adjustment or next_recommendation")
        if not _has_posts(result) and not _has_blockers(result):
            reasons.append("completion has no post evidence or blocker")

    return QualityGate(
        ok=not reasons,
        reasons=tuple(reasons),
        action="pass" if not reasons else "block",
    )


def _validate_blocker_report(result: dict[str, Any]) -> QualityGate:
    if _has_blockers(result):
        return QualityGate(ok=True, reasons=(), action="pass_blocker")
    return QualityGate(ok=False, reasons=("block action without blockers",), action="block")


def _attach_quality_gate(response: dict[str, Any], gate: QualityGate) -> None:
    result = response.get("result")
    if not isinstance(result, dict):
        return
    result["quality_gate"] = _gate_payload(gate)


def _gate_payload(gate: QualityGate) -> dict[str, Any]:
    return {
        "version": QUALITY_GATE_VERSION,
        "ok": gate.ok,
        "action": gate.action,
        "reasons": list(gate.reasons),
    }


def _main_update(response: dict[str, Any]) -> dict[str, Any]:
    direct = response.get("main_card_update")
    if isinstance(direct, dict):
        return direct
    result = response.get("result")
    if isinstance(result, dict) and isinstance(result.get("main_card_update"), dict):
        return result["main_card_update"]
    return {}


def _is_campaign_like(*, task_body: str | None, result: dict[str, Any], main_update: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(task_body or ""),
            str(main_update.get("card_type") or ""),
            str(main_update.get("business_phase") or ""),
            str(result.get("card_type") or ""),
            str(result.get("campaign") or ""),
        ]
    ).lower()
    if any(token in text for token in ("campaign", "posting", "growth", "cadence", "cycle window")):
        return True
    return bool(result.get("maintenance_loop") or result.get("mock_x_posts"))


def _has_meaningful(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_meaningful(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_meaningful(item) for item in value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _has_posts(result: dict[str, Any]) -> bool:
    posts = result.get("mock_x_posts")
    return isinstance(posts, list) and bool(posts)


def _has_blockers(result: dict[str, Any]) -> bool:
    blockers = result.get("blockers")
    return isinstance(blockers, list) and bool(blockers)
