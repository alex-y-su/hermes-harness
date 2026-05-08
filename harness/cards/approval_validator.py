#!/usr/bin/env python3
"""
Approval-card schema validator.

An approval card lives at /factory/approvals/<approval_id>.json and gates a
real-world side effect (tweet, email, ad, etc.) behind an explicit user
approval. See docs/cards/approval-flow.md for the contract.

Schema (mechanical):
    approval_id        matches ^appr-\\d{8}T\\d{6}Z-[0-9a-f]{4}$
    schema_version     == "1"
    kind               non-empty string (free-text; no closed enum by design)
    status             one of {pending, approved, rejected, posted,
                              post_failed, creds_missing}
    source_card_id     non-empty string
    proposed_at_utc    matches ^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z$
    payload            non-empty dict
                       (when kind=="tweet": payload.text is 1..280 chars)
    audit_trail        non-empty list of {event, at_utc, by} entries
    decided_at_utc     null OR matches utc regex
    resulting_artifact null OR dict

Usable two ways:

  1. As a module:
       from harness.cards.approval_validator import (
           validate_approval_shape, ApprovalValidationError,
       )
       validate_approval_shape(approval_dict)        # raises on failure

  2. As a CLI:
       python3 harness/cards/approval_validator.py path/to/appr-....json
       # exits 0 valid, 1 invalid; errors prefixed "ERROR:" on stderr
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path


APPROVAL_ID_PATTERN = re.compile(r"^appr-\d{8}T\d{6}Z-[0-9a-f]{4}$")
UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
ALLOWED_STATUSES = (
    "pending", "approved", "rejected", "posted", "post_failed", "creds_missing",
)


class ApprovalValidationError(Exception):
    """Raised when an approval card's shape does not satisfy the schema."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("approval invalid:\n" + "\n".join(errors))


def validate_approval_shape(card: dict) -> None:
    """Raise ApprovalValidationError if `card` does not satisfy the schema."""
    errs: list[str] = []

    def req(path: str, cond: bool, msg: str) -> None:
        if not cond:
            errs.append(f"  - {path}: {msg}")

    req("approval_id",
        isinstance(card.get("approval_id"), str)
        and bool(APPROVAL_ID_PATTERN.match(card.get("approval_id", "") or "")),
        r"must match ^appr-\d{8}T\d{6}Z-[0-9a-f]{4}$")

    req("schema_version",
        card.get("schema_version") == "1",
        'must be the string "1"')

    req("kind",
        isinstance(card.get("kind"), str) and bool(card.get("kind")),
        "non-empty string required (free-text descriptor)")

    req("status",
        card.get("status") in ALLOWED_STATUSES,
        f"must be one of {ALLOWED_STATUSES}")

    req("source_card_id",
        isinstance(card.get("source_card_id"), str)
        and bool(card.get("source_card_id")),
        "non-empty string required")

    req("proposed_at_utc",
        isinstance(card.get("proposed_at_utc"), str)
        and bool(UTC_PATTERN.match(card.get("proposed_at_utc", "") or "")),
        "must match utc-iso regex (e.g., 2026-05-08T22:00:45Z)")

    payload = card.get("payload")
    req("payload",
        isinstance(payload, dict) and len(payload) >= 1,
        "non-empty dict required")

    # tweet-specific payload check
    if card.get("kind") == "tweet" and isinstance(payload, dict):
        text = payload.get("text")
        if not (isinstance(text, str) and 1 <= len(text) <= 280):
            errs.append(
                "  - payload.text: when kind='tweet', must be a string of 1..280 chars"
            )

    audit = card.get("audit_trail")
    req("audit_trail",
        isinstance(audit, list) and len(audit) >= 1,
        "non-empty list required")
    if isinstance(audit, list):
        for i, entry in enumerate(audit):
            if not isinstance(entry, dict):
                errs.append(f"  - audit_trail[{i}]: must be a dict")
                continue
            req(f"audit_trail[{i}].event",
                isinstance(entry.get("event"), str) and bool(entry.get("event")),
                "non-empty string required")
            req(f"audit_trail[{i}].at_utc",
                isinstance(entry.get("at_utc"), str)
                and bool(UTC_PATTERN.match(entry.get("at_utc", "") or "")),
                "must match utc-iso regex")
            req(f"audit_trail[{i}].by",
                isinstance(entry.get("by"), str) and bool(entry.get("by")),
                "non-empty string required")

    # Optional fields with shape constraints when present.
    decided = card.get("decided_at_utc")
    if decided is not None:
        req("decided_at_utc",
            isinstance(decided, str) and bool(UTC_PATTERN.match(decided or "")),
            "must be null or match utc-iso regex")

    artifact = card.get("resulting_artifact")
    if artifact is not None:
        req("resulting_artifact",
            isinstance(artifact, dict),
            "must be null or a dict")

    if errs:
        raise ApprovalValidationError(errs)


def validate_approval_file(path: Path) -> None:
    if not path.is_file():
        raise ApprovalValidationError([f"  - file not found: {path}"])
    try:
        card = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ApprovalValidationError([f"  - json decode error: {e}"]) from e
    validate_approval_shape(card)


# ---- CLI ----

def _cli(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: approval_validator.py <path-to-approval.json>\n")
        return 2
    path = Path(argv[1])
    try:
        validate_approval_file(path)
    except ApprovalValidationError as e:
        for line in e.errors:
            sys.stderr.write(f"ERROR:{line}\n")
        return 1
    sys.stderr.write(f"approval '{path}' valid\n")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
