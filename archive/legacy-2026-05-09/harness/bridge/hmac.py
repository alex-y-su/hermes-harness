from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_body_hash(body: Any) -> str:
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def push_signature_payload(*, team_name: str, task_id: str, state: str, sequence: int | str, body_hash: str) -> str:
    return "\n".join([team_name, task_id, state, str(sequence), body_hash])


def sign_push(*, secret: str, team_name: str, task_id: str, state: str, sequence: int | str, body: Any) -> str:
    payload = push_signature_payload(
        team_name=team_name,
        task_id=task_id,
        state=state,
        sequence=sequence,
        body_hash=canonical_body_hash(body),
    )
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_push_signature(
    *,
    expected: str | None,
    secret: str,
    team_name: str,
    task_id: str,
    state: str,
    sequence: int | str,
    body: Any,
) -> bool:
    normalized = expected.removeprefix("sha256=") if expected else ""
    if not re.fullmatch(r"[a-fA-F0-9]{64}", normalized):
        return False
    actual = sign_push(secret=secret, team_name=team_name, task_id=task_id, state=state, sequence=sequence, body=body)
    return hmac.compare_digest(actual, normalized.lower())
