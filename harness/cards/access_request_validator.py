#!/usr/bin/env python3
"""
Access-request schema validator.

An access-request lives at /factory/access-requests/<request_id>.json and is
the bot's structured ask for credentials/access it needs to perform an
already-approved action. See docs/cards/approval-flow.md for the contract.

Schema (mechanical):
    request_id           matches ^accr-\\d{8}T\\d{6}Z-[0-9a-f]{4}$
    schema_version       == "1"
    kind                 non-empty string (free-text; no closed enum by design)
    status               one of {pending, granted, denied}
    resource_id          matches ^[a-z][a-z0-9_-]*\\/[a-z][a-z0-9_-]*$
    requested_at_utc     matches utc-iso regex
    what_we_need         string, len >= 30 (must be specific)
    why                  string, len >= 20
    blocking_approval_id null OR matches ^appr-\\d{8}T\\d{6}Z-[0-9a-f]{4}$
    audit_trail          non-empty list of {event, at_utc, by} entries

Usable two ways:

  1. As a module:
       from harness.cards.access_request_validator import (
           validate_access_request_shape, AccessRequestValidationError,
       )
       validate_access_request_shape(req_dict)       # raises on failure

  2. As a CLI:
       python3 harness/cards/access_request_validator.py path/to/accr-....json
       # exits 0 valid, 1 invalid; errors prefixed "ERROR:" on stderr
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path


REQUEST_ID_PATTERN = re.compile(r"^accr-\d{8}T\d{6}Z-[0-9a-f]{4}$")
APPROVAL_ID_PATTERN = re.compile(r"^appr-\d{8}T\d{6}Z-[0-9a-f]{4}$")
RESOURCE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*\/[a-z][a-z0-9_-]*$")
UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
ALLOWED_STATUSES = ("pending", "granted", "denied")


class AccessRequestValidationError(Exception):
    """Raised when an access-request's shape does not satisfy the schema."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("access-request invalid:\n" + "\n".join(errors))


def validate_access_request_shape(req: dict) -> None:
    """Raise AccessRequestValidationError if `req` does not satisfy the schema."""
    errs: list[str] = []

    def need(path: str, cond: bool, msg: str) -> None:
        if not cond:
            errs.append(f"  - {path}: {msg}")

    need("request_id",
         isinstance(req.get("request_id"), str)
         and bool(REQUEST_ID_PATTERN.match(req.get("request_id", "") or "")),
         r"must match ^accr-\d{8}T\d{6}Z-[0-9a-f]{4}$")

    need("schema_version",
         req.get("schema_version") == "1",
         'must be the string "1"')

    need("kind",
         isinstance(req.get("kind"), str) and bool(req.get("kind")),
         "non-empty string required (free-text descriptor)")

    need("status",
         req.get("status") in ALLOWED_STATUSES,
         f"must be one of {ALLOWED_STATUSES}")

    need("resource_id",
         isinstance(req.get("resource_id"), str)
         and bool(RESOURCE_ID_PATTERN.match(req.get("resource_id", "") or "")),
         r"must match ^<dir>/<name>$ (e.g., 'social/twitter')")

    need("requested_at_utc",
         isinstance(req.get("requested_at_utc"), str)
         and bool(UTC_PATTERN.match(req.get("requested_at_utc", "") or "")),
         "must match utc-iso regex (e.g., 2026-05-08T22:01:23Z)")

    need("what_we_need",
         isinstance(req.get("what_we_need"), str)
         and len(req.get("what_we_need", "")) >= 30,
         ">=30 chars required (must be specific about exactly what is needed)")

    need("why",
         isinstance(req.get("why"), str)
         and len(req.get("why", "")) >= 20,
         ">=20 chars required")

    if "blocking_approval_id" in req:
        bai = req.get("blocking_approval_id")
        if bai is not None:
            need("blocking_approval_id",
                 isinstance(bai, str) and bool(APPROVAL_ID_PATTERN.match(bai or "")),
                 r"must be null or match ^appr-\d{8}T\d{6}Z-[0-9a-f]{4}$")

    audit = req.get("audit_trail")
    need("audit_trail",
         isinstance(audit, list) and len(audit) >= 1,
         "non-empty list required")
    if isinstance(audit, list):
        for i, entry in enumerate(audit):
            if not isinstance(entry, dict):
                errs.append(f"  - audit_trail[{i}]: must be a dict")
                continue
            need(f"audit_trail[{i}].event",
                 isinstance(entry.get("event"), str) and bool(entry.get("event")),
                 "non-empty string required")
            need(f"audit_trail[{i}].at_utc",
                 isinstance(entry.get("at_utc"), str)
                 and bool(UTC_PATTERN.match(entry.get("at_utc", "") or "")),
                 "must match utc-iso regex")
            need(f"audit_trail[{i}].by",
                 isinstance(entry.get("by"), str) and bool(entry.get("by")),
                 "non-empty string required")

    if errs:
        raise AccessRequestValidationError(errs)


def validate_access_request_file(path: Path) -> None:
    if not path.is_file():
        raise AccessRequestValidationError([f"  - file not found: {path}"])
    try:
        req = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise AccessRequestValidationError([f"  - json decode error: {e}"]) from e
    validate_access_request_shape(req)


# ---- CLI ----

def _cli(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: access_request_validator.py <path-to-access-request.json>\n")
        return 2
    path = Path(argv[1])
    try:
        validate_access_request_file(path)
    except AccessRequestValidationError as e:
        for line in e.errors:
            sys.stderr.write(f"ERROR:{line}\n")
        return 1
    sys.stderr.write(f"access-request '{path}' valid\n")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
