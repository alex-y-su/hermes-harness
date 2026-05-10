#!/usr/bin/env python3
"""
Resource registry validator.

Each resource lives in /factory/resources/<kind>/<id>.json and declares the
shape of an external (or mocked) surface the team can act on.

Schema (mechanical):
    id            non-empty "<kind>/<name>" string ; kind matches the parent dir name
    kind          non-empty string
    title         string >= 5 chars
    state         one of {ready, not_ready, archived}  (no other values)
    description   string >= 10 chars
    execution     dict mapping action_name -> {skill | hub_skill: <string>, ...}
                  must be non-empty; each action must declare exactly one of
                  `skill` or `hub_skill` as a non-empty string.
    mock          bool (default False)
    auto_approved bool (default False)

If state == "ready" then `mock` MUST be explicit (no default acceptance) so
no real-surface action is ever attempted on something we forgot to flag.

Usable two ways:
    1. As a module:
         from resource_validator import validate_resource_shape, ResourceValidationError
    2. As a CLI:
         python3 /factory/lib/resource_validator.py path/to/resource.json
         # exit 0 valid, 1 invalid
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path


ALLOWED_STATES = ("ready", "not_ready", "archived")
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*/[a-z][a-z0-9_.-]*$")


class ResourceValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("resource invalid:\n" + "\n".join(errors))


def validate_resource_shape(res: dict, expected_id_prefix: str | None = None) -> None:
    """Raise ResourceValidationError if the resource dict does not satisfy the schema.

    Args:
        res: the parsed resource JSON.
        expected_id_prefix: if provided, the resource's `id` must start with
                            "<prefix>/" (used when validating a file under
                            /factory/resources/<prefix>/...). The `kind` field
                            is a free-text descriptor and is NOT required to
                            match the prefix.
    """
    errs: list[str] = []

    def req(path: str, cond: bool, msg: str) -> None:
        if not cond:
            errs.append(f"  - {path}: {msg}")

    rid = res.get("id")
    req("id",
        isinstance(rid, str) and bool(ID_PATTERN.match(rid or "")),
        r"must match ^<dir>/<name>$ (lowercase letters, digits, dashes/underscores)")

    kind = res.get("kind")
    req("kind", isinstance(kind, str) and bool(kind), "non-empty string required (free-text descriptor)")

    if expected_id_prefix is not None and isinstance(rid, str) and "/" in rid:
        req("id prefix matches dir",
            rid.split("/", 1)[0] == expected_id_prefix,
            f"id must start with '{expected_id_prefix}/' to match parent directory")

    req("title",
        isinstance(res.get("title"), str) and len(res.get("title", "")) >= 5,
        ">=5 chars required")

    state = res.get("state")
    req("state",
        state in ALLOWED_STATES,
        f"must be one of {ALLOWED_STATES}")

    req("description",
        isinstance(res.get("description"), str) and len(res.get("description", "")) >= 10,
        ">=10 chars required")

    exe = res.get("execution")
    req("execution",
        isinstance(exe, dict) and len(exe) >= 1,
        "non-empty dict of action_name -> action_config required")
    if isinstance(exe, dict):
        for action_name, cfg in exe.items():
            if not isinstance(cfg, dict):
                errs.append(f"  - execution.{action_name}: must be a dict")
                continue
            skill = cfg.get("skill") or cfg.get("hub_skill")
            req(f"execution.{action_name}.skill|hub_skill",
                isinstance(skill, str) and bool(skill),
                "must declare exactly one of `skill` or `hub_skill` as a non-empty string")

    mock = res.get("mock")
    req("mock",
        isinstance(mock, bool),
        "must be an explicit boolean (not absent) — the mock flag is load-bearing safety")

    auto = res.get("auto_approved")
    if "auto_approved" in res:
        req("auto_approved",
            isinstance(auto, bool),
            "must be a boolean if present")

    if errs:
        raise ResourceValidationError(errs)


def validate_resource_file(path: Path) -> None:
    """Validate a resource JSON file at path, inferring expected_kind from the
    parent directory under /factory/resources/."""
    if not path.is_file():
        raise ResourceValidationError([f"  - file not found: {path}"])
    try:
        res = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ResourceValidationError([f"  - json decode error: {e}"]) from e
    expected_id_prefix = path.parent.name if path.parent.name not in ("resources", "_archive") else None
    validate_resource_shape(res, expected_id_prefix=expected_id_prefix)


# ---- CLI ----

def _cli(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: resource_validator.py <path-to-resource.json> [more...]\n")
        return 2
    rc = 0
    for arg in argv[1:]:
        path = Path(arg)
        try:
            validate_resource_file(path)
            sys.stderr.write(f"resource '{path}' valid\n")
        except ResourceValidationError as e:
            sys.stderr.write(f"resource '{path}' INVALID:\n{e}\n")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
