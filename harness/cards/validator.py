#!/usr/bin/env python3
"""
Card schema validator for the verifiable-outcome card model.

A card is valid if it has the SHAPE the operator and reviewer expect.
There are no enums of types, methods, or roles — the validator only
checks that every required slot is filled with non-trivial content.

Usable two ways:

  1. As a module:
       from card_validator import validate_card_shape, CardValidationError
       validate_card_shape(card_dict)              # raises on failure

  2. As a CLI:
       python3 /factory/lib/card_validator.py path/to/card.json
       # exits 0 on valid, 1 on invalid
       # writes structured errors to stderr

The validator never touches the board, never makes side effects.
It is pure shape-check.
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path


class CardValidationError(Exception):
    """Raised when a card's shape does not satisfy the schema."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("card invalid:\n" + "\n".join(errors))


# Marker tokens that make a verification step "objectively checkable".
# At least one must appear in step.describe (case-insensitive).
# This forbids steps like "the video is faith-friendly" that no
# deterministic or even LLM reviewer can verify rigorously.
OBJECTIVE_MARKERS = (
    "url", "http", "fetch", "page",
    "file", "exist", "present", "disk", "path",
    "log", "logged", "delivery", "outbox",
    "count", "rows", "size", "bytes", "length",
    "hash", "checksum",
    "status", "200", "404", "5xx",
    "contain", "contains", "match", "matches", "regex",
    "json", "yaml", "schema",
)


def validate_card_shape(card: dict) -> None:
    """Raise CardValidationError if `card` does not satisfy the schema.

    Required fields:
      - id: non-empty string
      - title: string >= 5 chars
      - outcome.describe_artifact: string >= 40 chars
      - outcome.locator_field: string matching ^result\\.<name>$
      - outcome.verification_steps: non-empty list, each with:
          - describe: string >= 20 chars containing at least one OBJECTIVE_MARKERS token
          - evidence_required: string >= 20 chars
      - pipeline: non-empty list, each with:
          - role: non-empty string
          - describe_contribution: string >= 20 chars
      - pipeline[-1].role MUST equal "reviewer"
      - The locator-field name (after "result.") MUST appear in at least
        one non-reviewer pipeline step's describe_contribution
    """
    errs: list[str] = []

    def req(path: str, cond: bool, msg: str) -> None:
        if not cond:
            errs.append(f"  - {path}: {msg}")

    req("id", isinstance(card.get("id"), str) and bool(card.get("id")),
        "missing or non-string")
    req("title",
        isinstance(card.get("title"), str) and len(card.get("title", "")) >= 5,
        ">=5 chars required")

    o = card.get("outcome") or {}
    req("outcome.describe_artifact",
        isinstance(o.get("describe_artifact"), str) and len(o.get("describe_artifact", "")) >= 40,
        ">=40 chars required")
    req("outcome.locator_field",
        isinstance(o.get("locator_field"), str)
        and bool(re.match(r"^result\.[a-zA-Z_][\w.]*$", o.get("locator_field", "") or "")),
        r"must match ^result\.<field>")

    steps = o.get("verification_steps") or []
    req("outcome.verification_steps",
        isinstance(steps, list) and len(steps) >= 1,
        "non-empty list required")
    for i, s in enumerate(steps):
        req(f"outcome.verification_steps[{i}].describe",
            isinstance(s.get("describe"), str) and len(s.get("describe", "")) >= 20,
            ">=20 chars required")
        req(f"outcome.verification_steps[{i}].evidence_required",
            isinstance(s.get("evidence_required"), str) and len(s.get("evidence_required", "")) >= 20,
            ">=20 chars required")
        # Objectivity check: must contain at least one objective marker
        if isinstance(s.get("describe"), str):
            dl = s["describe"].lower()
            if not any(tok in dl for tok in OBJECTIVE_MARKERS):
                errs.append(
                    f"  - outcome.verification_steps[{i}].describe: must contain at least one "
                    f"objective marker so the reviewer can pick a deterministic check "
                    f"(e.g., URL, file, log, contains, hash, status, count, regex, schema). "
                    f"Subjective checks are forbidden."
                )

    pipe = card.get("pipeline") or []
    req("pipeline", isinstance(pipe, list) and len(pipe) >= 1,
        "non-empty list required")
    for i, p in enumerate(pipe):
        req(f"pipeline[{i}].role",
            isinstance(p.get("role"), str) and bool(p.get("role")),
            "non-empty string required")
        req(f"pipeline[{i}].describe_contribution",
            isinstance(p.get("describe_contribution"), str) and len(p.get("describe_contribution", "")) >= 20,
            ">=20 chars required")
    if pipe:
        req("pipeline[-1].role",
            pipe[-1].get("role") == "reviewer",
            "last pipeline step must have role='reviewer'")

    locator_name = (o.get("locator_field") or "").replace("result.", "")
    if pipe and locator_name:
        early_text = " ".join(p.get("describe_contribution", "") for p in pipe[:-1])
        req("pipeline (locator referenced)",
            locator_name in early_text,
            f"locator field '{locator_name}' must be referenced by some non-reviewer step's describe_contribution")

    if errs:
        raise CardValidationError(errs)


# ============================================================
# CLI
# ============================================================

def _cli(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: card_validator.py <path-to-card.json>\n")
        return 2
    path = Path(argv[1])
    if not path.is_file():
        sys.stderr.write(f"file not found: {path}\n")
        return 2
    try:
        card = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.stderr.write(f"json decode error: {e}\n")
        return 2
    try:
        validate_card_shape(card)
    except CardValidationError as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    sys.stderr.write(f"card '{card.get('id')}' valid\n")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
