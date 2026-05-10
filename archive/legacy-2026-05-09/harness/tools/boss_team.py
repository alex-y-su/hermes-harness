from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

from harness import boss_team


def _json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _request_json(method: str, hub_url: str, path: str, token: str | None, body: dict[str, Any] | None = None) -> Any:
    url = hub_url.rstrip("/") + path
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=payload, headers=headers, method=method)
    with request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def _list_tenants(hub_url: str, token: str | None) -> list[dict[str, Any]]:
    data = _request_json("GET", hub_url, "/v1/tenants", token)
    if isinstance(data, dict) and isinstance(data.get("tenants"), list):
        return data["tenants"]
    if isinstance(data, list):
        return data
    raise RuntimeError(f"unexpected tenant list response: {data!r}")


def cmd_install_local(args: argparse.Namespace) -> int:
    result = boss_team.install_local_boss_team(
        Path(args.factory).expanduser().resolve(),
        Path(args.home_root).expanduser().resolve(),
        overwrite=args.overwrite,
        layout=args.layout,
    )
    _json(result)
    return 0


def cmd_verify_local(args: argparse.Namespace) -> int:
    result = boss_team.verify_local_boss_team(
        Path(args.factory).expanduser().resolve(),
        Path(args.home_root).expanduser().resolve(),
        layout=args.layout,
    )
    _json(result)
    return 0 if result["ok"] else 1


def cmd_hub_plan(args: argparse.Namespace) -> int:
    _json({"tenants": boss_team.hub_tenant_payloads(base_domain=args.base_domain)})
    return 0


def cmd_verify_hub(args: argparse.Namespace) -> int:
    tenants = _list_tenants(args.hub_url, args.token)
    result = boss_team.verify_hub_tenants(tenants)
    result["actual"] = [tenant.get("id") for tenant in tenants]
    _json(result)
    return 0 if result["ok"] else 1


def cmd_apply_hub(args: argparse.Namespace) -> int:
    tenants = _list_tenants(args.hub_url, args.token)
    existing = {tenant.get("id") for tenant in tenants}
    created = []
    skipped = []
    for payload in boss_team.hub_tenant_payloads(base_domain=args.base_domain):
        if payload["id"] in existing:
            skipped.append(payload["id"])
            continue
        try:
            _request_json("POST", args.hub_url, "/v1/tenants", args.token, payload)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"failed to create tenant {payload['id']}: HTTP {exc.code}: {detail}") from exc
        created.append(payload["id"])
    tenants = _list_tenants(args.hub_url, args.token)
    result = boss_team.verify_hub_tenants(tenants)
    result.update({"created": created, "skipped": skipped, "actual": [tenant.get("id") for tenant in tenants]})
    _json(result)
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install and verify the canonical Hermes Harness boss team.")
    sub = parser.add_subparsers(dest="command", required=True)

    local = sub.add_parser("install-local", help="Write local profile homes and factory directories.")
    local.add_argument("--factory", required=True)
    local.add_argument("--home-root", default=str(Path.home()))
    local.add_argument("--layout", choices=["legacy", "hermes-profiles"], default="legacy")
    local.add_argument("--overwrite", action="store_true")
    local.set_defaults(func=cmd_install_local)

    verify_local = sub.add_parser("verify-local", help="Verify local profile homes and factory directories.")
    verify_local.add_argument("--factory", required=True)
    verify_local.add_argument("--home-root", default=str(Path.home()))
    verify_local.add_argument("--layout", choices=["legacy", "hermes-profiles"], default="legacy")
    verify_local.set_defaults(func=cmd_verify_local)

    plan = sub.add_parser("hub-plan", help="Print canonical hub tenant payloads.")
    plan.add_argument("--base-domain", default="hermes.local")
    plan.set_defaults(func=cmd_hub_plan)

    verify_hub = sub.add_parser("verify-hub", help="Verify a hub has canonical boss-team tenants.")
    verify_hub.add_argument("--hub-url", required=True)
    verify_hub.add_argument("--token", default=None)
    verify_hub.set_defaults(func=cmd_verify_hub)

    apply_hub = sub.add_parser("apply-hub", help="Create missing canonical boss-team tenants in a hub.")
    apply_hub.add_argument("--hub-url", required=True)
    apply_hub.add_argument("--token", default=None)
    apply_hub.add_argument("--base-domain", default="hermes.local")
    apply_hub.set_defaults(func=cmd_apply_hub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
