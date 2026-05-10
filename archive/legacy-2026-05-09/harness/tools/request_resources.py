from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from harness import db
from harness.resources import list_resources
from harness.tools.common import add_factory_args, paths


REQUESTABLE_STATES = {"missing", "needs-access", "needs-setup", "blocked", "declined", "denied"}

FIELD_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "production_app_config": [
        {"name": "app_repo_url", "type": "string", "description": "Repository or admin location for the production app config."},
        {"name": "config_path", "type": "string", "description": "Exact config or feature-flag path where this resource is changed."},
        {"name": "release_process", "type": "string", "description": "How changes are deployed to production."},
        {"name": "rollback_process", "type": "string", "description": "How to safely revert a bad change."},
    ],
    "database": [
        {"name": "connection_secret_location", "type": "string", "description": "Where the connection string should be installed, without exposing it in tickets."},
        {"name": "allowed_scope", "type": "string", "description": "What data can be read or changed and what is off-limits."},
        {"name": "approval_to_use", "type": "boolean", "description": "Whether agents may use this connection."},
    ],
    "external_accounts": [
        {"name": "accounts", "type": "string", "description": "Which external accounts exist and should be used."},
        {"name": "access_method", "type": "string", "description": "How agents should obtain access or route drafts/actions."},
        {"name": "approval_policy", "type": "string", "description": "Which actions require explicit approval."},
    ],
    "paid_channel": [
        {"name": "accounts", "type": "string", "description": "Which paid accounts exist."},
        {"name": "budget_cap", "type": "string", "description": "Maximum spend allowed before renewed approval."},
        {"name": "approval_to_prepare", "type": "boolean", "description": "Whether agents may prepare campaigns without launching spend."},
    ],
    "analytics": [
        {"name": "analytics_source", "type": "string", "description": "Where product/growth metrics are available."},
        {"name": "key_metrics", "type": "string", "description": "The metrics agents should optimize."},
        {"name": "access_method", "type": "string", "description": "How agents should access the dashboard, export, or API."},
    ],
    "product_mod": [
        {"name": "mod_scope", "type": "string", "description": "What the mod may include: theme, templates, content, rooms, copy, flags."},
        {"name": "constraints", "type": "string", "description": "Brand, safety, content, or product constraints."},
        {"name": "definition_of_ready", "type": "string", "description": "What must exist before production ingestion can be approved."},
    ],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create user requests for file-backed resources that are not ready.")
    add_factory_args(parser)
    parser.add_argument("--tag", default=None, help="Stable suffix for generated request IDs")
    parser.add_argument("--json", action="store_true")
    return parser


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip("/")).strip("-").lower()


def _fields(resource: dict[str, Any]) -> list[dict[str, str]]:
    return FIELD_TEMPLATES.get(str(resource.get("kind") or "")) or [
        {"name": "resource_details", "type": "string", "description": "What exists, what is missing, and how agents should access or use this resource."},
        {"name": "approval_policy", "type": "string", "description": "Which actions require explicit approval."},
    ]


def _request_id(resource_id: str, tag: str) -> str:
    return f"resource-{_slug(resource_id)}-required-{tag}"


def _decode_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _existing_open_request(conn: Any, resource_id: str) -> str | None:
    for row in db.list_approval_requests(conn, status="open"):
        if row["kind"] != "resource-required":
            continue
        metadata = _decode_metadata(row["metadata"])
        if metadata.get("resource_id") == resource_id:
            return str(row["request_id"])
    return None


def run(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    tag = args.tag or "latest"
    created: list[str] = []
    existing: list[str] = []
    skipped: list[str] = []
    with db.session(db_path) as conn:
        for resource in list_resources(factory):
            state = str(resource.get("state") or "")
            resource_id = str(resource.get("id") or "")
            if state not in REQUESTABLE_STATES:
                skipped.append(resource_id)
                continue
            request_id = _existing_open_request(conn, resource_id)
            if request_id:
                _annotate_resource_file(resource, request_id)
                existing.append(request_id)
                continue
            request_id = _request_id(resource_id, tag)
            title = str(resource.get("title") or resource_id)
            team_name = str(resource.get("owner") or "boss")
            description = str(resource.get("description") or resource.get("body") or title)
            prompt = (
                f"Resource `{resource_id}` is currently `{state}`. Provide the missing data, access route, "
                "constraints, and approval policy before teams create downstream work that depends on it. "
                "Until this is supplied, agents must not request approval for production/public/paid/credentialed "
                f"actions against this resource.\n\nResource description: {description}"
            )
            db.upsert_approval_request(
                conn,
                request_id=request_id,
                assignment_id=f"resource:{resource_id}",
                team_name=team_name,
                task_id=None,
                kind="resource-required",
                title=f"Provide resource details: {title}",
                prompt=prompt,
                required_fields=_fields(resource),
                metadata={
                    "resources": [resource_id],
                    "resource_id": resource_id,
                    "resource_state": state,
                    "resource_kind": resource.get("kind") or "resource",
                    "mode": "resource-gate",
                    "decision": {
                        "requested_action": f"Provide missing setup/access details for {resource_id}",
                        "target_resource": resource_id,
                        "why": "Downstream autonomous work depends on this resource and should not create impossible approval cards.",
                        "blast_radius": "No external action is taken by this request; it only records required access/details.",
                        "fallback": "Keep dependent work internal-only and create setup/readiness tickets.",
                        "preconditions": ["Resource file exists", f"Resource state is {state}"],
                    },
                },
            )
            _annotate_resource_file(resource, request_id)
            created.append(request_id)
    return {"created": created, "existing": existing, "skipped": skipped, "count": len(created)}


def _annotate_resource_file(resource: dict[str, Any], request_id: str) -> None:
    path = Path(str(resource.get("path") or ""))
    if path.suffix.lower() != ".json" or not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data["user_request_id"] = request_id
        data["state_reason"] = "waiting on user-supplied resource details/access"
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    args = build_parser().parse_args()
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"created {result['count']} resource requests")


if __name__ == "__main__":
    main()
