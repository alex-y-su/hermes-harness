from __future__ import annotations

import argparse
import fcntl
import json
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from harness.resources import get_resource, normalize_resource_id
from harness.tools.common import add_factory_args, paths


COUNTED_STATUSES = {"committed", "failed_counted"}
RESERVED_STATUS = "reserved"
RELEASED_STATUSES = {"released", "failed_uncommitted"}
CARD_STATES = {"pending", "ready", "approval-required", "blocked", "completed", "released", "failed"}


@dataclass(frozen=True)
class GateContext:
    factory: Path
    resource_id: str
    action: str
    ticket_id: str
    artifact: str | None = None
    now: datetime | None = None

    @property
    def current_time(self) -> datetime:
        return self.now or datetime.now(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate and log usage of shared factory resources.")
    add_factory_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("check", "reserve"):
        cmd = sub.add_parser(name, help=f"{name} a resource action")
        _add_gate_args(cmd)
        cmd.add_argument("--json", action="store_true")

    commit = sub.add_parser("commit", help="Mark a reservation/action as externally committed")
    commit.add_argument("--resource", required=True)
    commit.add_argument("--action", required=True)
    commit.add_argument("--ticket-id", required=True)
    commit.add_argument("--reservation-id", default=None)
    commit.add_argument("--external-ref", default=None)
    commit.add_argument("--metadata", default=None, help="JSON object")
    commit.add_argument("--json", action="store_true")

    release = sub.add_parser("release", help="Release a reservation without counting usage")
    release.add_argument("--resource", required=True)
    release.add_argument("--action", required=True)
    release.add_argument("--ticket-id", required=True)
    release.add_argument("--reservation-id", required=True)
    release.add_argument("--reason", default=None)
    release.add_argument("--json", action="store_true")

    card = sub.add_parser("card", help="Create or gate hub-side resource action cards")
    card_sub = card.add_subparsers(dest="card_command", required=True)

    create = card_sub.add_parser("create", help="Create a pending resource action card")
    create.add_argument("--resource", required=True)
    create.add_argument("--action", required=True)
    create.add_argument("--ticket-id", required=True)
    create.add_argument("--team", required=True)
    create.add_argument("--artifact", required=True)
    create.add_argument("--why", required=True)
    create.add_argument("--title", default=None)
    create.add_argument("--metadata", default=None, help="JSON object")
    create.add_argument("--json", action="store_true")

    gate = card_sub.add_parser("gate", help="Run the gate for a pending resource action card")
    gate.add_argument("card", help="Card path or card id")
    gate.add_argument("--now", default=None, help="ISO timestamp for deterministic tests")
    gate.add_argument("--json", action="store_true")

    return parser


def _add_gate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--resource", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--artifact", default=None)
    parser.add_argument("--now", default=None, help="ISO timestamp for deterministic tests")


def run(args: argparse.Namespace) -> dict[str, Any]:
    factory, _db_path = paths(args)
    if args.command == "check":
        return check(
            GateContext(
                factory=factory,
                resource_id=args.resource,
                action=args.action,
                ticket_id=args.ticket_id,
                artifact=args.artifact,
                now=_parse_datetime(args.now) if args.now else None,
            )
        )
    if args.command == "reserve":
        return reserve(
            GateContext(
                factory=factory,
                resource_id=args.resource,
                action=args.action,
                ticket_id=args.ticket_id,
                artifact=args.artifact,
                now=_parse_datetime(args.now) if args.now else None,
            )
        )
    if args.command == "commit":
        return commit_usage(
            factory=factory,
            resource_id=args.resource,
            action=args.action,
            ticket_id=args.ticket_id,
            reservation_id=args.reservation_id,
            external_ref=args.external_ref,
            metadata=_load_json_object(args.metadata),
        )
    if args.command == "release":
        return release_usage(
            factory=factory,
            resource_id=args.resource,
            action=args.action,
            ticket_id=args.ticket_id,
            reservation_id=args.reservation_id,
            reason=args.reason,
        )
    if args.command == "card" and args.card_command == "create":
        return create_card(
            factory=factory,
            resource_id=args.resource,
            action=args.action,
            ticket_id=args.ticket_id,
            team=args.team,
            artifact=args.artifact,
            why=args.why,
            title=args.title,
            metadata=_load_json_object(args.metadata),
        )
    if args.command == "card" and args.card_command == "gate":
        return gate_card(factory=factory, card_ref=args.card, now=_parse_datetime(args.now) if args.now else None)
    raise SystemExit(f"unknown command: {args.command}")


def check(ctx: GateContext) -> dict[str, Any]:
    resource = get_resource(ctx.factory, ctx.resource_id)
    if resource is None:
        decision = _decision(ctx, "blocked", reason="resource_not_found", next_step="create_resource_file")
        return _write_decision(ctx.factory, decision)
    ctx = GateContext(
        factory=ctx.factory,
        resource_id=normalize_resource_id(str(resource.get("id") or ctx.resource_id)),
        action=ctx.action,
        ticket_id=ctx.ticket_id,
        artifact=ctx.artifact,
        now=ctx.now,
    )
    policy = _action_policy(resource, ctx.action)
    if str(resource.get("state") or "") != "ready":
        decision = _decision(
            ctx,
            "blocked",
            reason="resource_not_ready",
            resource=resource,
            next_step="request_resource_details",
        )
        return _write_decision(ctx.factory, decision)
    if policy is None:
        decision = _decision(
            ctx,
            "blocked",
            reason="missing_action_policy",
            resource=resource,
            next_step="define_usage_policy",
        )
        return _write_decision(ctx.factory, decision)

    ledger = _read_ledger(ctx.factory, ctx.resource_id)
    decision = _evaluate_policy(ctx, resource, policy, ledger)
    return _write_decision(ctx.factory, decision)


def reserve(ctx: GateContext) -> dict[str, Any]:
    with _resource_lock(ctx.factory, ctx.resource_id):
        result = check(ctx)
        if result["decision"] not in {"allowed", "requires_approval"}:
            _append_usage(
                ctx.factory,
                ctx.resource_id,
                {
                    "ts": _iso(ctx.current_time),
                    "resource_id": normalize_resource_id(ctx.resource_id),
                    "action": ctx.action,
                    "ticket_id": ctx.ticket_id,
                    "status": "blocked",
                    "reason": result.get("reason"),
                    "decision_path": result.get("decision_path"),
                },
            )
            return result
        reservation_id = f"rsv-{uuid.uuid4().hex[:12]}"
        ttl_minutes = int((result.get("policy") or {}).get("reservation_ttl_minutes") or 10)
        expires_at = ctx.current_time + timedelta(minutes=ttl_minutes)
        usage = {
            "ts": _iso(ctx.current_time),
            "resource_id": normalize_resource_id(ctx.resource_id),
            "action": ctx.action,
            "ticket_id": ctx.ticket_id,
            "artifact": ctx.artifact,
            "status": RESERVED_STATUS,
            "reservation_id": reservation_id,
            "expires_at": _iso(expires_at),
            "decision_path": result.get("decision_path"),
        }
        _append_usage(ctx.factory, ctx.resource_id, usage)
        result = {
            **result,
            "reservation_id": reservation_id,
            "expires_at": _iso(expires_at),
        }
        return _write_decision(ctx.factory, result)


def commit_usage(
    *,
    factory: Path,
    resource_id: str,
    action: str,
    ticket_id: str,
    reservation_id: str | None = None,
    external_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    with _resource_lock(factory, resource_id):
        entry = {
            "ts": _iso(now),
            "resource_id": normalize_resource_id(resource_id),
            "action": action,
            "ticket_id": ticket_id,
            "status": "committed",
            "reservation_id": reservation_id,
            "external_ref": external_ref,
            "metadata": metadata or {},
        }
        _append_usage(factory, resource_id, entry)
    return {"status": "committed", "entry": entry}


def release_usage(
    *,
    factory: Path,
    resource_id: str,
    action: str,
    ticket_id: str,
    reservation_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    with _resource_lock(factory, resource_id):
        entry = {
            "ts": _iso(now),
            "resource_id": normalize_resource_id(resource_id),
            "action": action,
            "ticket_id": ticket_id,
            "status": "released",
            "reservation_id": reservation_id,
            "reason": reason,
        }
        _append_usage(factory, resource_id, entry)
    return {"status": "released", "entry": entry}


def create_card(
    *,
    factory: Path,
    resource_id: str,
    action: str,
    ticket_id: str,
    team: str,
    artifact: str,
    why: str,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card_id = _card_id(ticket_id, resource_id, action)
    card = {
        "card_id": card_id,
        "status": "pending",
        "ticket_id": ticket_id,
        "team": team,
        "resource_id": normalize_resource_id(resource_id),
        "action": action,
        "artifact": artifact,
        "why": why,
        "title": title or f"{action} on {resource_id}",
        "created_at": _iso(datetime.now(UTC)),
        "metadata": metadata or {},
    }
    path = _card_dir(factory, "pending") / f"{card_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"card": card, "path": str(path)}


def gate_card(*, factory: Path, card_ref: str, now: datetime | None = None) -> dict[str, Any]:
    path = _resolve_card_path(factory, card_ref)
    card = json.loads(path.read_text(encoding="utf-8"))
    ctx = GateContext(
        factory=factory,
        resource_id=card["resource_id"],
        action=card["action"],
        ticket_id=card["ticket_id"],
        artifact=card.get("artifact"),
        now=now,
    )
    decision = reserve(ctx)
    target_state = {
        "allowed": "ready",
        "requires_approval": "approval-required",
    }.get(decision.get("decision"), "blocked")
    card.update(
        {
            "status": target_state,
            "gated_at": _iso(datetime.now(UTC)),
            "gate_decision": decision,
            "reservation_id": decision.get("reservation_id"),
            "available_at": decision.get("available_at"),
        }
    )
    target = _card_dir(factory, target_state) / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if path.resolve() != target.resolve():
        path.unlink(missing_ok=True)
    return {"card": card, "path": str(target), "decision": decision}


def _evaluate_policy(
    ctx: GateContext,
    resource: dict[str, Any],
    policy: dict[str, Any],
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    now = ctx.current_time
    constraints: list[dict[str, Any]] = []

    quiet = _quiet_hours_available_at(policy, now)
    if quiet is not None:
        constraints.append({"reason": "quiet_hours", "available_at": quiet})

    interval_minutes = _number(policy.get("min_interval_minutes"))
    observation_days = _number(policy.get("observation_window_days"))
    if observation_days is not None:
        interval_minutes = max(interval_minutes or 0, observation_days * 24 * 60)
    if interval_minutes:
        last = _last_counted_at(ledger, ctx.action, now)
        if last is not None:
            available_at = last + timedelta(minutes=interval_minutes)
            if available_at > now:
                constraints.append(
                    {
                        "reason": "cooldown",
                        "last_used_at": _iso(last),
                        "min_interval_minutes": interval_minutes,
                        "available_at": available_at,
                    }
                )

    for key, value in policy.items():
        parsed = _parse_window_limit(key)
        if parsed is None:
            continue
        limit, window = int(value), parsed
        window_start = now - window
        counted = _counted_entries(ledger, ctx.action, now, since=window_start)
        if len(counted) >= limit:
            available_at = min(_entry_available_after_window(entry, window) for entry in counted if entry.get("ts"))
            constraints.append(
                {
                    "reason": "quota_depleted",
                    "used": len(counted),
                    "limit": limit,
                    "window_seconds": int(window.total_seconds()),
                    "available_at": available_at,
                }
            )

    if constraints:
        latest = max(item["available_at"] for item in constraints)
        primary = max(constraints, key=lambda item: item["available_at"])
        return _decision(
            ctx,
            "blocked",
            reason=str(primary["reason"]),
            resource=resource,
            policy=policy,
            available_at=latest,
            constraints=constraints,
            next_step=str(policy.get("overage_action") or "schedule_later"),
        )

    if _requires_approval(resource, policy):
        return _decision(ctx, "requires_approval", resource=resource, policy=policy, next_step="request_user_approval")
    return _decision(ctx, "allowed", resource=resource, policy=policy, next_step="execute_on_hub")


def _action_policy(resource: dict[str, Any], action: str) -> dict[str, Any] | None:
    usage_policy = resource.get("usage_policy")
    if not isinstance(usage_policy, dict):
        return None
    actions = usage_policy.get("actions")
    if not isinstance(actions, dict):
        return None
    policy = actions.get(action)
    return policy if isinstance(policy, dict) else None


def _requires_approval(resource: dict[str, Any], policy: dict[str, Any]) -> bool:
    if policy.get("requires_approval") is not None:
        return bool(policy.get("requires_approval"))
    text = str(resource.get("approval_policy") or "").lower()
    return "require" in text or "approval" in text


def _decision(
    ctx: GateContext,
    decision: str,
    *,
    reason: str | None = None,
    resource: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    available_at: datetime | None = None,
    constraints: list[dict[str, Any]] | None = None,
    next_step: str | None = None,
) -> dict[str, Any]:
    result = {
        "decision": decision,
        "reason": reason,
        "resource_id": normalize_resource_id(ctx.resource_id),
        "resource_state": resource.get("state") if resource else None,
        "action": ctx.action,
        "ticket_id": ctx.ticket_id,
        "artifact": ctx.artifact,
        "checked_at": _iso(ctx.current_time),
        "available_at": _iso(available_at) if available_at else None,
        "next_step": next_step,
        "policy": policy or {},
        "constraints": [_serialize_constraint(item) for item in constraints or []],
    }
    return {key: value for key, value in result.items() if value is not None}


def _serialize_constraint(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (_iso(value) if isinstance(value, datetime) else value)
        for key, value in item.items()
    }


def _write_decision(factory: Path, decision: dict[str, Any]) -> dict[str, Any]:
    checked_at = _parse_datetime(decision["checked_at"])
    path = (
        factory
        / "resource_gate_decisions"
        / checked_at.date().isoformat()
        / f"{_slug(decision['ticket_id'])}__{_slug(decision['resource_id'])}__{_slug(decision['action'])}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    decision = {**decision, "decision_path": str(path)}
    path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return decision


def _read_ledger(factory: Path, resource_id: str) -> list[dict[str, Any]]:
    path = _ledger_path(factory, resource_id)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _append_usage(factory: Path, resource_id: str, entry: dict[str, Any]) -> None:
    path = _ledger_path(factory, resource_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _ledger_path(factory: Path, resource_id: str) -> Path:
    return factory / "resource_usage" / f"{normalize_resource_id(resource_id)}.jsonl"


@contextmanager
def _resource_lock(factory: Path, resource_id: str):
    lock = factory / "locks" / "resources" / f"{_slug(resource_id)}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _counted_entries(
    ledger: list[dict[str, Any]],
    action: str,
    now: datetime,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    released = {
        str(entry.get("reservation_id"))
        for entry in ledger
        if entry.get("status") in RELEASED_STATUSES and entry.get("reservation_id")
    }
    committed_reservations = {
        str(entry.get("reservation_id"))
        for entry in ledger
        if entry.get("status") in COUNTED_STATUSES and entry.get("reservation_id")
    }
    counted = []
    for entry in ledger:
        if entry.get("action") != action:
            continue
        ts_raw = entry.get("ts")
        if not ts_raw:
            continue
        ts = _parse_datetime(str(ts_raw))
        if since is not None and ts < since:
            continue
        status = entry.get("status")
        reservation_id = str(entry.get("reservation_id") or "")
        if status in COUNTED_STATUSES:
            counted.append(entry)
        elif status == RESERVED_STATUS:
            if reservation_id in released or reservation_id in committed_reservations:
                continue
            expires = _parse_datetime(str(entry.get("expires_at"))) if entry.get("expires_at") else ts
            if expires > now:
                counted.append(entry)
    return counted


def _entry_available_after_window(entry: dict[str, Any], window: timedelta) -> datetime:
    if entry.get("status") == RESERVED_STATUS and entry.get("expires_at"):
        return _parse_datetime(str(entry["expires_at"]))
    return _parse_datetime(str(entry["ts"])) + window


def _last_counted_at(ledger: list[dict[str, Any]], action: str, now: datetime) -> datetime | None:
    times = [_parse_datetime(str(entry["ts"])) for entry in _counted_entries(ledger, action, now) if entry.get("ts")]
    return max(times) if times else None


def _parse_window_limit(key: str) -> timedelta | None:
    match = re.fullmatch(r"max_per_(\d+)?(m|h|d)", key)
    if match:
        count = int(match.group(1) or "1")
        unit = match.group(2)
        if unit == "m":
            return timedelta(minutes=count)
        if unit == "h":
            return timedelta(hours=count)
        return timedelta(days=count)
    aliases = {
        "max_per_hour": timedelta(hours=1),
        "max_per_24h": timedelta(hours=24),
        "max_per_day": timedelta(days=1),
        "max_per_7d": timedelta(days=7),
        "max_per_30d": timedelta(days=30),
    }
    return aliases.get(key)


def _quiet_hours_available_at(policy: dict[str, Any], now: datetime) -> datetime | None:
    quiet = policy.get("quiet_hours_local")
    if not isinstance(quiet, dict):
        return None
    start = _parse_time(str(quiet.get("start") or ""))
    end = _parse_time(str(quiet.get("end") or ""))
    if start is None or end is None:
        return None
    tz = ZoneInfo(str(quiet.get("timezone") or "UTC"))
    local = now.astimezone(tz)
    local_time = local.time().replace(second=0, microsecond=0)
    if start <= end:
        in_quiet = start <= local_time < end
        available_date = local.date()
    else:
        in_quiet = local_time >= start or local_time < end
        available_date = local.date() + (timedelta(days=1) if local_time >= start else timedelta())
    if not in_quiet:
        return None
    available_local = datetime.combine(available_date, end, tzinfo=tz)
    if available_local <= local:
        available_local += timedelta(days=1)
    return available_local.astimezone(UTC)


def _parse_time(value: str) -> time | None:
    try:
        hour, minute = value.split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except Exception:
        return None


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _number(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _load_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit("metadata must be a JSON object")
    return data


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip("/")).strip("-").lower()


def _card_id(ticket_id: str, resource_id: str, action: str) -> str:
    return f"{_slug(ticket_id)}__{_slug(resource_id)}__{_slug(action)}"


def _card_dir(factory: Path, state: str) -> Path:
    if state not in CARD_STATES:
        raise ValueError(f"invalid card state: {state}")
    return factory / "resource_action_cards" / state


def _resolve_card_path(factory: Path, card_ref: str) -> Path:
    path = Path(card_ref)
    if path.exists():
        return path
    for state in CARD_STATES:
        candidate = _card_dir(factory, state) / f"{card_ref}.json"
        if candidate.exists():
            return candidate
    raise SystemExit(f"unknown resource action card: {card_ref}")


def main() -> None:
    args = build_parser().parse_args()
    result = run(args)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
