from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from harness import db
from harness.factory import utc_now, write_json
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a user response for an approval/input/auth request.")
    add_factory_args(parser)
    parser.add_argument("request_id")
    parser.add_argument("--response-json", required=True, help="JSON response to store on the request")
    parser.add_argument("--status", choices=["supplied", "resuming", "resolved", "denied"], default="supplied")
    parser.add_argument("--no-continuation", action="store_true", help="Only store the response; do not queue resume work")
    parser.add_argument("--continuation-assignment-id", default=None)
    return parser


def _parse_response(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise SystemExit(f"--response-json must be valid JSON: {error}") from error


def _decode_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["required_fields"] = json.loads(data.pop("required_fields_json") or "[]")
    data["response"] = json.loads(data.pop("response_json") or "null")
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:80] or "request"


def _default_continuation_id(request: dict[str, Any]) -> str:
    digest = hashlib.sha1(request["request_id"].encode("utf-8")).hexdigest()[:10]
    return f"{_slug(request['assignment_id'])}-resume-{digest}"


def _write_continuation_assignment(
    *,
    factory: Path,
    request: dict[str, Any],
    response: Any,
    assignment_id: str,
) -> Path:
    team_dir = factory / "teams" / request["team_name"]
    if not team_dir.exists():
        raise SystemExit(f"team does not exist for continuation: {request['team_name']}")
    inbox_path = team_dir / "inbox" / f"{assignment_id}.md"
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    if not inbox_path.exists():
        inbox_path.write_text(
            "# Resume blocked assignment\n\n"
            f"- assignment_id: {assignment_id}\n"
            f"- parent_assignment_id: {request['assignment_id']}\n"
            f"- user_request_id: {request['request_id']}\n"
            f"- team: {request['team_name']}\n"
            f"- created_at: {utc_now()}\n\n"
            "## Blocked Request\n\n"
            f"{request['prompt']}\n\n"
            "## User Response\n\n"
            f"```json\n{json.dumps(response, indent=2, sort_keys=True)}\n```\n\n"
            "Continue the blocked work using the supplied response. Do not ask again unless new input is strictly required.\n",
            encoding="utf-8",
        )
    write_json(
        inbox_path.with_suffix(".queued.json"),
        {
            "assignment_id": assignment_id,
            "parent_assignment_id": request["assignment_id"],
            "user_request_id": request["request_id"],
            "team": request["team_name"],
            "state": "queued",
            "created_at": utc_now(),
        },
    )
    return inbox_path


def run(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    response = _parse_response(args.response_json)
    with db.session(db_path) as conn:
        request_row = conn.execute("SELECT * FROM approval_requests WHERE request_id = ?", (args.request_id,)).fetchone()
        if request_row is None:
            raise SystemExit(f"unknown user request: {args.request_id}")
        request = _decode_row(request_row)
        existing_resume = db.get_assignment_resume_by_request(conn, args.request_id)
        metadata = {"resume": "stored user response"}
        final_status = args.status
        should_continue = not getattr(args, "no_continuation", False) and args.status in {"supplied", "resuming"}
        if should_continue:
            continuation_id = (
                args.continuation_assignment_id
                or (existing_resume["continuation_assignment_id"] if existing_resume else None)
                or request["metadata"].get("continuation_assignment_id")
            )
            continuation_id = str(continuation_id or _default_continuation_id(request))
            inbox_path = _write_continuation_assignment(
                factory=factory,
                request=request,
                response=response,
                assignment_id=continuation_id,
            )
            db.upsert_assignment(
                conn,
                assignment_id=continuation_id,
                team_name=request["team_name"],
                status="queued",
                inbox_path=str(inbox_path),
                order_id=request["assignment_id"],
            )
            resume = db.upsert_assignment_resume(
                conn,
                resume_id=f"resume-{hashlib.sha1(request['request_id'].encode('utf-8')).hexdigest()[:16]}",
                request_id=request["request_id"],
                parent_assignment_id=request["assignment_id"],
                continuation_assignment_id=continuation_id,
                team_name=request["team_name"],
                status="sent",
                response=response,
                strategy="continuation_assignment",
                metadata={"continuation_path": str(inbox_path)},
            )
            if existing_resume is None:
                db.record_event(
                    conn,
                    team_name=request["team_name"],
                    assignment_id=continuation_id,
                    source="harness.resolve_user_request",
                    kind="user-request-continuation",
                    state="resuming",
                    payload_path=str(inbox_path),
                    metadata={"request_id": request["request_id"], "parent_assignment_id": request["assignment_id"]},
                )
            db.clear_assignment_blocker(conn, assignment_id=request["assignment_id"], status="resuming")
            metadata.update(
                {
                    "resume": "queued continuation assignment",
                    "resume_strategy": "continuation_assignment",
                    "continuation_assignment_id": continuation_id,
                    "continuation_path": str(inbox_path),
                    "resume_id": resume["resume_id"],
                }
            )
            final_status = "resuming"
        else:
            resume = db.upsert_assignment_resume(
                conn,
                resume_id=f"resume-{hashlib.sha1(request['request_id'].encode('utf-8')).hexdigest()[:16]}",
                request_id=request["request_id"],
                parent_assignment_id=request["assignment_id"],
                continuation_assignment_id=None,
                team_name=request["team_name"],
                status=args.status,
                response=response,
                strategy="none",
                metadata={"no_continuation": getattr(args, "no_continuation", False)},
            )
            metadata["resume_id"] = resume["resume_id"]
        row = db.resolve_approval_request(
            conn,
            request_id=args.request_id,
            response=response,
            status=final_status,
            metadata=metadata,
        )
        if row is None:
            raise SystemExit(f"unknown user request: {args.request_id}")
        return _decode_row(row)


def main(argv: list[str] | None = None) -> None:
    result = run(build_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
