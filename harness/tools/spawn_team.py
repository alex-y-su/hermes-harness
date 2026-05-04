from __future__ import annotations

import argparse
import asyncio
import os

from harness import db
from harness.factory import append_journal, copy_template, load_template, read_json, team_path, utc_now, write_json
from harness.models import SubstrateHandle
from harness.substrate.factory import build_driver
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a remote-team folder and provision/boot its substrate.")
    add_factory_args(parser)
    parser.add_argument("name")
    parser.add_argument("--template", choices=["single-agent", "multi-agent", "single-agent-team", "multi-agent-team"], default="single-agent")
    parser.add_argument("--substrate", choices=["e2b", "external"], default="external")
    parser.add_argument("--dry-run", action="store_true", help="Do not contact E2B; create local state only")
    parser.add_argument("--agent-card-url", default=None, help="External substrate AgentCard URL")
    parser.add_argument("--push-url", default=os.getenv("BOSS_PUSH_URL"), help="Public boss push URL")
    parser.add_argument("--brief", default="", help="Team brief text")
    parser.add_argument("--criteria", default="", help="Acceptance criteria text")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser


async def run(args: argparse.Namespace) -> dict[str, str]:
    factory, db_path = paths(args)
    if args.substrate == "e2b" and not args.dry_run and not args.push_url:
        raise SystemExit("BOSS_PUSH_URL/--push-url is required for real E2B teams")

    template = load_template(args.template)
    team_dir = team_path(factory, args.name)
    push_url = args.push_url or "http://localhost:8787/a2a/push"
    variables = {
        "TEAM_NAME": args.name,
        "TEMPLATE_NAME": template.name,
        "BRIEF": args.brief or f"{args.name} remote team.",
        "CRITERIA": args.criteria or "Complete assigned work and report artifacts through outbox.",
        "PUSH_URL": push_url,
        "SUBSTRATE": args.substrate,
    }
    copy_template(template, team_dir, variables)

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
            metadata={**handle.metadata, "boot_mode": template.boot_mode, "workspace_path": str(team_dir)},
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
        },
    )
    append_journal(team_dir / "journal.md", f"spawned via {args.substrate} substrate")

    with db.session(db_path) as conn:
        db.save_substrate_handle(conn, handle, status="booted")
        db.record_event(
            conn,
            team_name=args.name,
            source="hr.spawn_team",
            kind="spawned",
            state="spawned",
            metadata={"template": template.name, "substrate": args.substrate, "dry_run": args.dry_run},
        )
    return {"team": args.name, "path": str(team_dir), "agent_card_url": agent_card_url}


def main(argv: list[str] | None = None) -> None:
    result = asyncio.run(run(build_parser().parse_args(argv)))
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
