from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from harness import db
from harness.factory import load_template, read_json, team_path, write_json
from harness.bridge.secrets import SecretResolver
from harness.substrate.factory import build_driver
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision and boot one per-assignment sandbox.")
    add_factory_args(parser)
    parser.add_argument("team")
    parser.add_argument("assignment_id")
    parser.add_argument("--dry-run", action="store_true", help="Do not contact E2B")
    parser.add_argument("--env", default=None, help="External bridge .env for resolving push secrets")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("HARNESS_ASSIGNMENT_E2B_TIMEOUT_SECONDS", "3600")),
    )
    return parser


def _template_name(team_dir: Path) -> str:
    status_path = team_dir / "status.json"
    if status_path.exists():
        status = read_json(status_path)
        template = status.get("template")
        if isinstance(template, str) and template.strip():
            return template.strip()
    if (team_dir / "internal" / "profiles").exists():
        return "multi-agent-team"
    return "single-agent-team"


def _assignment_metadata(team_dir: Path, assignment_id: str) -> dict:
    queued_path = team_dir / "inbox" / f"{assignment_id}.queued.json"
    if queued_path.exists():
        return read_json(queued_path)
    return {}


def _restore_workspace_from_archive(*, team_dir: Path, restore_source: str | None) -> None:
    if not restore_source:
        return
    source = Path(restore_source)
    if not source.exists() or not source.is_dir():
        raise SystemExit(f"sandbox restore source does not exist: {restore_source}")
    for path in source.iterdir():
        if path.name == "assignment-sandbox.json":
            continue
        target = team_dir / path.name
        if path.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(path, target)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


async def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    return await run_for_assignment(
        factory=factory,
        db_path=db_path,
        team=args.team,
        assignment_id=args.assignment_id,
        dry_run=args.dry_run,
        env_path=args.env,
        timeout_seconds=args.timeout_seconds,
    )


async def run_for_assignment(
    *,
    factory: Path,
    db_path: Path,
    team: str,
    assignment_id: str,
    dry_run: bool = False,
    env_path: str | Path | None = None,
    secret_resolver: SecretResolver | None = None,
    timeout_seconds: int = int(os.getenv("HARNESS_ASSIGNMENT_E2B_TIMEOUT_SECONDS", "3600")),
) -> dict[str, str]:
    team_dir = team_path(factory, team)
    if not team_dir.exists():
        raise SystemExit(f"team does not exist: {team}")

    assignment_metadata = _assignment_metadata(team_dir, assignment_id)
    restore_source = assignment_metadata.get("sandbox_restore_source")
    restore_strategy = assignment_metadata.get("resume_strategy")
    _restore_workspace_from_archive(team_dir=team_dir, restore_source=restore_source)

    template = load_template(_template_name(team_dir))
    transport = read_json(team_dir / "transport.json")
    resolver = secret_resolver or SecretResolver(env_path)
    remote_env = build_remote_env(transport, resolver, team)
    driver = build_driver(
        "e2b",
        dry_run=dry_run,
        remote_env=remote_env,
        api_key=resolver.resolve("env://E2B_API_KEY"),
    )
    handle = await driver.provision(team, team_dir, template, timeout_seconds)
    handle = type(handle)(
        team_name=handle.team_name,
        substrate=handle.substrate,
        handle=handle.handle,
        metadata={
            **handle.metadata,
            "assignment_id": assignment_id,
            "boot_mode": template.boot_mode,
            "workspace_path": str(team_dir),
            "restore_source": restore_source,
            "restore_strategy": restore_strategy,
        },
    )
    agent_card_url = await driver.boot(handle)

    sandbox_path = team_dir / "inbox" / f"{assignment_id}.sandbox.json"
    payload = {
        "assignment_id": assignment_id,
        "team_name": team,
        "sandbox_id": handle.handle,
        "substrate": handle.substrate,
        "agent_card_url": agent_card_url,
        "handle": asdict(handle),
    }
    write_json(sandbox_path, payload)

    with db.session(db_path) as conn:
        db.save_assignment_sandbox(
            conn,
            assignment_id=assignment_id,
            team_name=team,
            handle=handle,
            agent_card_url=agent_card_url,
            status="restored" if restore_source else "booted",
            metadata={
                "sandbox_path": str(sandbox_path),
                "dry_run": dry_run,
                "restore_source": restore_source,
                "restore_strategy": restore_strategy,
            },
        )
        db.record_event(
            conn,
            team_name=team,
            assignment_id=assignment_id,
            source="run_assignment_sandbox",
            kind="assignment-sandbox-restored" if restore_source else "assignment-sandbox-booted",
            state="restored" if restore_source else "booted",
            payload_path=str(sandbox_path),
            metadata={
                "dry_run": dry_run,
                "template": template.name,
                "restore_source": restore_source,
                "restore_strategy": restore_strategy,
            },
        )

    return {
        "team_name": team,
        "assignment_id": assignment_id,
        "sandbox_id": handle.handle,
        "agent_card_url": agent_card_url,
        "path": str(sandbox_path),
    }


def build_remote_env(transport: dict, resolver: SecretResolver, team_name: str) -> dict[str, str]:
    push_url = str(transport.get("push_url") or "")
    if not push_url:
        raise SystemExit(f"team {team_name} transport.json is missing push_url")
    return {
        "BOSS_PUSH_URL": push_url,
        "HARNESS_REMOTE_TEAM_NAME": team_name,
        "HARNESS_REMOTE_PUSH_TOKEN": resolver.resolve(transport.get("push_token_ref")) or "",
        "HARNESS_REMOTE_BRIDGE_SECRET": resolver.resolve(transport.get("bridge_secret_ref")) or "",
    }


def main(argv: list[str] | None = None) -> None:
    result = asyncio.run(run(build_parser().parse_args(argv)))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
