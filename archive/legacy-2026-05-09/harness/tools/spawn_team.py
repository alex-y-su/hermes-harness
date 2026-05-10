from __future__ import annotations

import argparse
import asyncio
import os
import secrets
from pathlib import Path

from harness import db
from harness.factory import append_journal, copy_template, load_template, read_json, require_team_name, team_path, utc_now, write_json
from harness.models import SubstrateHandle
from harness.substrate.factory import build_driver
from harness.tools.common import add_factory_args, paths


def _read_blueprint_dir(path: Path) -> dict[str, str]:
    parts: list[str] = []
    for filename in ("blueprint.yaml", "AGENTS.md", "brief.md", "TEAM_SOUL.md", "criteria.md"):
        candidate = path / filename
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            parts.append(f"## {filename}\n\n{text}")
    if not parts:
        raise FileNotFoundError(f"blueprint directory has no readable contract files: {path}")
    brief_path = path / "brief.md"
    criteria_path = path / "criteria.md"
    team_soul_path = path / "TEAM_SOUL.md"
    return {
        "text": "\n\n".join(parts).strip() + "\n",
        "brief": brief_path.read_text(encoding="utf-8").strip() if brief_path.is_file() else "",
        "criteria": criteria_path.read_text(encoding="utf-8").strip() if criteria_path.is_file() else "",
        "team_soul": team_soul_path.read_text(encoding="utf-8").strip() if team_soul_path.is_file() else "",
    }


def resolve_blueprint(factory: Path, value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    has_separator = "/" in value or "\\" in value
    raw_path = Path(value).expanduser()
    if raw_path.is_absolute() or has_separator:
        path = raw_path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"blueprint path does not exist: {path}")
        name = path.stem if path.is_file() else path.name
    else:
        name = require_team_name(value)
        candidates = (factory / "team_blueprints" / name, factory / "team_blueprints" / f"{name}.md")
        path = next((candidate for candidate in candidates if candidate.exists()), None)  # type: ignore[assignment]
        if path is None:
            raise FileNotFoundError(f"unknown team blueprint: {name}")
    if path.is_dir():
        data = _read_blueprint_dir(path)
    elif path.is_file():
        text = path.read_text(encoding="utf-8").strip() + "\n"
        data = {"text": text, "brief": text, "criteria": "", "team_soul": ""}
    else:
        raise FileNotFoundError(f"blueprint is neither a file nor directory: {path}")
    return {"name": name, "path": str(path), **data}


def render_hired_team_soul(team_name: str, blueprint: dict[str, str]) -> str:
    source = blueprint.get("team_soul") or blueprint["text"]
    return (
        f"# {team_name} Remote Team Soul\n\n"
        "You are a hired Hermes Harness remote team running on E2B, not a local hub-machine Hermes profile.\n\n"
        "Execution boundary:\n"
        "- Active reasoning and tool work happen on E2B.\n"
        "- The hub keeps assignments, status, transport metadata, artifacts, and audit records under factory/teams/<name>/.\n"
        "- Communicate with the boss team through A2A and the factory bridge.\n"
        "- Use Codex OAuth through provider openai-codex. Do not use OpenRouter or direct OpenAI API keys.\n"
        "- Obey /factory/HARD_RULES.md and /factory/STANDING_APPROVALS.md before outbound work.\n\n"
        f"Blueprint source: {blueprint['path']}\n\n"
        "## Hiring Blueprint\n\n"
        f"{source.strip()}\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a remote-team folder and provision/boot its substrate.")
    add_factory_args(parser)
    parser.add_argument("name")
    parser.add_argument("--template", choices=["single-agent", "multi-agent", "single-agent-team", "multi-agent-team"], default="single-agent")
    parser.add_argument("--substrate", choices=["e2b", "external"], default="external")
    parser.add_argument("--dry-run", action="store_true", help="Do not contact E2B; create local state only")
    parser.add_argument("--agent-card-url", default=None, help="External substrate AgentCard URL")
    parser.add_argument("--push-url", default=os.getenv("BOSS_PUSH_URL"), help="Public boss push URL")
    parser.add_argument("--blueprint", default=None, help="Blueprint name under factory/team_blueprints or an explicit blueprint file/directory")
    parser.add_argument("--brief", default="", help="Team brief text")
    parser.add_argument("--criteria", default="", help="Acceptance criteria text")
    parser.add_argument("--env", default=os.getenv("HARNESS_ENV_PATH") or os.getenv("HERMES_BRIDGE_ENV_FILE"))
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser


async def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    if args.substrate == "e2b" and not args.dry_run and not args.push_url:
        raise SystemExit("BOSS_PUSH_URL/--push-url is required for real E2B teams")

    blueprint = resolve_blueprint(factory, getattr(args, "blueprint", None))
    template = load_template(args.template)
    team_dir = team_path(factory, args.name)
    push_url = args.push_url or "http://localhost:8787/a2a/push"
    brief = args.brief or f"{args.name} remote team."
    criteria = args.criteria or "Complete assigned work and report artifacts through outbox."
    if blueprint:
        if args.brief:
            brief = f"{args.brief.strip()}\n\n## Hiring Blueprint\n\n{blueprint['text'].strip()}"
        else:
            brief = blueprint.get("brief") or blueprint["text"]
        if args.criteria:
            criteria = f"{args.criteria.strip()}\n\n## Blueprint Criteria\n\n{(blueprint.get('criteria') or blueprint['text']).strip()}"
        else:
            criteria = blueprint.get("criteria") or criteria
    variables = {
        "TEAM_NAME": args.name,
        "TEMPLATE_NAME": template.name,
        "BRIEF": brief,
        "CRITERIA": criteria,
        "PUSH_URL": push_url,
        "SUBSTRATE": args.substrate,
    }
    copy_template(template, team_dir, variables)
    if blueprint:
        (team_dir / "context").mkdir(parents=True, exist_ok=True)
        (team_dir / "context" / "hiring_blueprint.md").write_text(blueprint["text"], encoding="utf-8")
        (team_dir / "TEAM_SOUL.md").write_text(render_hired_team_soul(args.name, blueprint), encoding="utf-8")
        (team_dir / "brief.md").write_text(brief.rstrip() + "\n", encoding="utf-8")
        (team_dir / "criteria.md").write_text(criteria.rstrip() + "\n", encoding="utf-8")

    team_env_prefix = args.name.upper().replace("-", "_")
    env_arg = getattr(args, "env", None)
    secrets_added = ensure_team_secrets(
        env_path=Path(env_arg).expanduser() if env_arg else None,
        keys=(f"HARNESS_TEAM_{team_env_prefix}_BEARER_TOKEN", f"HARNESS_TEAM_{team_env_prefix}_PUSH_TOKEN"),
    )

    if args.substrate == "e2b":
        handle = SubstrateHandle(
            team_name=args.name,
            substrate="e2b",
            handle=f"e2b-team://{args.name}",
            metadata={
                "boot_mode": template.boot_mode,
                "workspace_path": str(team_dir),
                "per_assignment": True,
                "dry_run": bool(args.dry_run),
                "blueprint": blueprint["name"] if blueprint else None,
                "blueprint_path": blueprint["path"] if blueprint else None,
                "secrets_added": secrets_added,
            },
        )
        agent_card_url = args.agent_card_url or ""
    else:
        driver = build_driver(args.substrate, dry_run=args.dry_run, agent_card_url=args.agent_card_url)
        handle = await driver.provision(args.name, team_dir, template, args.timeout_seconds)
        handle = type(handle)(
            team_name=handle.team_name,
            substrate=handle.substrate,
            handle=handle.handle,
            metadata={
                **handle.metadata,
                "boot_mode": template.boot_mode,
                "workspace_path": str(team_dir),
                "blueprint": blueprint["name"] if blueprint else None,
                "blueprint_path": blueprint["path"] if blueprint else None,
            },
        )
        agent_card_url = await driver.boot(handle)

    transport_path = team_dir / "transport.json"
    transport = read_json(transport_path)
    transport.update(
        {
            "protocol": "a2a",
            "substrate": args.substrate,
            "agent_card_url": agent_card_url,
            "push_url": push_url,
            "per_assignment": args.substrate == "e2b",
            "team_bearer_token_ref": f"env://HARNESS_TEAM_{args.name.upper().replace('-', '_')}_BEARER_TOKEN",
            "push_token_ref": f"env://HARNESS_TEAM_{args.name.upper().replace('-', '_')}_PUSH_TOKEN",
            "bridge_secret_ref": "env://HARNESS_BRIDGE_SECRET",
            "substrate_handle_ref": f"sqlite://substrate_handles/{args.name}",
            "blueprint": blueprint["name"] if blueprint else None,
            "blueprint_path": blueprint["path"] if blueprint else None,
        }
    )
    write_json(transport_path, transport)
    write_json(
        team_dir / "status.json",
        {
            "team_name": args.name,
            "state": "spawned",
            "template": template.name,
            "substrate": args.substrate,
            "agent_card_url": agent_card_url,
            "updated_at": utc_now(),
            "dry_run": bool(args.dry_run),
            "blueprint": blueprint["name"] if blueprint else None,
            "blueprint_path": blueprint["path"] if blueprint else None,
            "secrets_added": secrets_added,
        },
    )
    journal_line = f"spawned via {args.substrate} substrate"
    if blueprint:
        journal_line += f" from blueprint {blueprint['name']}"
    append_journal(team_dir / "journal.md", journal_line)

    with db.session(db_path) as conn:
        db.save_substrate_handle(conn, handle, status="booted")
        db.record_event(
            conn,
            team_name=args.name,
            source="hr.spawn_team",
            kind="spawned",
            state="spawned",
            metadata={
                "template": template.name,
                "substrate": args.substrate,
                "dry_run": args.dry_run,
                "blueprint": blueprint["name"] if blueprint else None,
                "blueprint_path": blueprint["path"] if blueprint else None,
                "secrets_added": secrets_added,
            },
        )
    return {"team": args.name, "path": str(team_dir), "agent_card_url": agent_card_url}


def ensure_team_secrets(*, env_path: Path | None, keys: tuple[str, str]) -> list[str]:
    if env_path is None:
        return []
    existing: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            existing[key.strip()] = value.strip()
    missing = [key for key in keys if not existing.get(key) and not os.getenv(key)]
    if not missing:
        return []
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with env_path.open("a", encoding="utf-8") as handle:
        if env_path.exists() and env_path.stat().st_size:
            handle.write("\n")
        for key in missing:
            handle.write(f"{key}={secrets.token_urlsafe(32)}\n")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass
    return missing


def main(argv: list[str] | None = None) -> None:
    result = asyncio.run(run(build_parser().parse_args(argv)))
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
