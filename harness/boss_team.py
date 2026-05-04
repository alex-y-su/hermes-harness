from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class BossProfile:
    name: str
    hub_tenant_id: str
    role: str
    runtime: str
    summary: str


BOSS_PROFILES: tuple[BossProfile, ...] = (
    BossProfile("boss", "boss", "strategy", "llm", "Forms strategy and writes orders."),
    BossProfile("supervisor", "supervisor", "approval", "llm", "Signs in-envelope work and escalates novel work."),
    BossProfile("hr", "hr_profile", "routing", "llm", "Routes approved orders to remote teams and manages lifecycle."),
    BossProfile("conductor", "conductor", "cadence", "llm", "Owns cron cadence, health checks, and throughput balance."),
    BossProfile("critic", "critic", "review", "llm", "Reviews deliverables before they are accepted by the boss team."),
    BossProfile("a2a-bridge", "a2a_bridge", "transport", "daemon", "Runs the factory to A2A bridge and writes heartbeats."),
)

PROFILE_CONFIG: dict[str, Any] = {
    "model": {
        "provider": "openai-codex",
        "default": "gpt-5.3-codex",
        "base_url": "https://chatgpt.com/backend-api/codex",
    },
    "agent": {"max_turns": 500},
    "goals": {"max_turns": 1000},
    "compression": {"threshold": 0.70},
    "approvals": {"mode": "off"},
    "hooks_auto_accept": True,
    "delegation": {"max_iterations": 200},
}

FACTORY_DIRS: tuple[str, ...] = (
    "orders",
    "approved_orders",
    "assignments",
    "inbox",
    "outbox",
    "status",
    "drafts",
    "approvals",
    "decisions",
    "escalations",
    "locks",
    "teams",
)

HUB_TENANT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")


def profile_names() -> list[str]:
    return [profile.name for profile in BOSS_PROFILES]


def profile_by_name(name: str) -> BossProfile:
    for profile in BOSS_PROFILES:
        if profile.name == name:
            return profile
    raise KeyError(name)


def profile_home(home_root: Path, profile: BossProfile, *, layout: str = "legacy") -> Path:
    if layout == "legacy":
        return home_root / f".hermes-{profile.name}"
    if layout == "hermes-profiles":
        return home_root / "profiles" / profile.name
    raise ValueError(f"unsupported boss-team profile layout: {layout}")


def _write_text(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def render_config(profile: BossProfile) -> str:
    daemon_line = "  daemon: harness-a2a-bridge\n" if profile.runtime == "daemon" else ""
    return (
        f"profile_name: {profile.name}\n"
        f"role: {profile.role}\n"
        f"runtime: {profile.runtime}\n"
        "model:\n"
        "  provider: openai-codex\n"
        "  default: gpt-5.3-codex\n"
        "  base_url: https://chatgpt.com/backend-api/codex\n"
        "agent:\n"
        "  max_turns: 500\n"
        "goals:\n"
        "  max_turns: 1000\n"
        "compression:\n"
        "  threshold: 0.70\n"
        "approvals:\n"
        "  mode: \"off\"\n"
        "hooks_auto_accept: true\n"
        "delegation:\n"
        "  max_iterations: 200\n"
        f"{daemon_line}"
    )


def render_agents(profile: BossProfile, factory_dir: Path, home_dir: Path) -> str:
    return (
        f"# AGENTS.md for {profile.name}\n\n"
        "Read these files at session start:\n"
        f"1. {home_dir}/SOUL.md\n"
        f"2. {factory_dir}/PROTOCOL.md\n"
        f"3. {factory_dir}/HARD_RULES.md\n"
        f"4. {factory_dir}/STANDING_APPROVALS.md\n"
        f"5. {home_dir}/TEAM_SOUL.md\n"
        f"6. {factory_dir}/PRIORITIZE.md\n"
        f"7. {factory_dir}/QUIET_HOURS.md\n\n"
        f"Factory: {factory_dir}\n"
        f"Profile: {profile.name}\n"
        f"Role: {profile.role}\n"
        f"Runtime: {profile.runtime}\n"
    )


def render_soul(profile: BossProfile) -> str:
    if profile.name == "a2a-bridge":
        body = (
            "You are the transport daemon profile. You do not perform LLM reasoning cycles.\n"
            "Keep the local factory bus and A2A remote-team protocol in sync, write heartbeats, "
            "honor HALT_a2a-bridge.flag, and avoid inventing strategy.\n"
        )
    elif profile.name == "boss":
        body = (
            "You are boss, the single public entry point for the Hermes Harness boss team.\n"
            "Your job: Forms strategy, writes orders, coordinates internal boss-team roles, "
            "and presents their work to the external user.\n"
            "When a user asks who you are, how many people are in your team, or what your team "
            "does, answer as the Hermes Harness boss-team coordinator. Do not say you are just "
            "one assistant in chat.\n"
            "The boss team has exactly six profiles: boss, supervisor, hr, conductor, critic, "
            "and a2a-bridge. Only boss is user-facing; supervisor, hr, conductor, critic, and "
            "a2a-bridge are internal roles behind the local factory bus.\n"
            "Work through the factory bus, leave auditable artifacts, continue until criteria "
            "are met or a hard blocker is recorded, and escalate only when the protocol requires it.\n"
        )
    else:
        body = (
            f"You are {profile.name}, the Hermes Harness {profile.role} profile.\n"
            f"Your job: {profile.summary}\n"
            "Work through the factory bus, leave auditable artifacts, continue until criteria "
            "are met or a hard blocker is recorded, and escalate only when the protocol requires it.\n"
        )
    return f"# {profile.name} SOUL\n\n{body}"


def render_team_soul(profile: BossProfile) -> str:
    body = (
        f"# {profile.name} TEAM_SOUL\n\n"
        "You are part of the generic Hermes Harness boss team: boss, supervisor, hr, "
        "conductor, critic, and a2a-bridge. The boss team owns orchestration for remote "
        "teams but stays domain-neutral. Use project-specific context from orders, "
        "assignments, and team briefs rather than embedding product-specific assumptions.\n"
    )
    if profile.name == "boss":
        body += (
            "\n"
            "User-facing identity rule: for direct A2A chat, boss speaks for the boss team. "
            "If asked about team size, say there are six boss-team profiles and name them. "
            "Clarify that only boss is exposed to the user; the other profiles coordinate "
            "internally through the factory bus.\n"
        )
    return body


def write_profile_bundle(
    profile: BossProfile,
    factory_dir: Path,
    home_root: Path,
    *,
    overwrite: bool = False,
    layout: str = "legacy",
) -> dict[str, Any]:
    home_dir = profile_home(home_root, profile, layout=layout)
    home_dir.mkdir(parents=True, exist_ok=True)
    written = []
    skipped = []
    files = {
        "AGENTS.md": render_agents(profile, factory_dir, home_dir),
        "config.yaml": render_config(profile),
        "SOUL.md": render_soul(profile),
        "TEAM_SOUL.md": render_team_soul(profile),
    }
    for name, content in files.items():
        path = home_dir / name
        if _write_text(path, content, overwrite):
            written.append(str(path))
        else:
            skipped.append(str(path))
    return {"profile": profile.name, "home": str(home_dir), "written": written, "skipped": skipped}


def install_local_boss_team(
    factory_dir: Path,
    home_root: Path,
    *,
    overwrite: bool = False,
    layout: str = "legacy",
) -> dict[str, Any]:
    factory_dir.mkdir(parents=True, exist_ok=True)
    for dirname in FACTORY_DIRS:
        (factory_dir / dirname).mkdir(parents=True, exist_ok=True)
    for profile in BOSS_PROFILES:
        (factory_dir / "inbox" / profile.name).mkdir(parents=True, exist_ok=True)
        (factory_dir / "outbox" / profile.name).mkdir(parents=True, exist_ok=True)
    bundles = [
        write_profile_bundle(profile, factory_dir, home_root, overwrite=overwrite)
        if layout == "legacy"
        else write_profile_bundle(profile, factory_dir, home_root, overwrite=overwrite, layout=layout)
        for profile in BOSS_PROFILES
    ]
    return {"factory": str(factory_dir), "profiles": profile_names(), "layout": layout, "bundles": bundles}


def verify_local_boss_team(factory_dir: Path, home_root: Path, *, layout: str = "legacy") -> dict[str, Any]:
    missing: list[str] = []
    mismatches: list[str] = []
    for dirname in FACTORY_DIRS:
        if not (factory_dir / dirname).is_dir():
            missing.append(f"factory/{dirname}")
    for profile in BOSS_PROFILES:
        home_dir = profile_home(home_root, profile, layout=layout)
        for filename in ("AGENTS.md", "config.yaml", "SOUL.md", "TEAM_SOUL.md"):
            path = home_dir / filename
            if not path.is_file():
                missing.append(str(path))
        config = home_dir / "config.yaml"
        if config.exists():
            text = config.read_text(encoding="utf-8")
            required = (
                f"profile_name: {profile.name}",
                f"role: {profile.role}",
                f"runtime: {profile.runtime}",
                "max_turns: 500",
                "max_turns: 1000",
                "hooks_auto_accept: true",
                "max_iterations: 200",
                "provider: openai-codex",
                "default: gpt-5.3-codex",
            )
            for needle in required:
                if needle not in text:
                    mismatches.append(f"{config}: missing {needle!r}")
            if "threshold: 0.70" not in text and "threshold: 0.7" not in text:
                mismatches.append(f"{config}: missing compression threshold 0.70")
            if (
                "mode: off" not in text
                and "mode: 'off'" not in text
                and 'mode: "off"' not in text
            ):
                mismatches.append(f"{config}: missing approvals mode 'off'")
        soul = home_dir / "TEAM_SOUL.md"
        if soul.exists() and "Jesuscord" in soul.read_text(encoding="utf-8"):
            mismatches.append(f"{soul}: contains domain-specific Jesuscord text")
    return {
        "ok": not missing and not mismatches,
        "profiles": profile_names(),
        "layout": layout,
        "missing": missing,
        "mismatches": mismatches,
    }


def render_hub_tenant_payload(profile: BossProfile, *, base_domain: str = "hermes.local") -> dict[str, Any]:
    if not HUB_TENANT_ID_RE.match(profile.hub_tenant_id):
        raise ValueError(f"invalid hub tenant id for {profile.name}: {profile.hub_tenant_id}")
    return {
        "id": profile.hub_tenant_id,
        "displayName": f"Hermes Boss Team: {profile.name}",
        "publicHost": f"{profile.hub_tenant_id}.{base_domain}",
        "browser": {"enabled": False},
        "quotas": {"memoryMax": "1G", "cpuQuota": "100%"},
        "auth": {"jwtSubjects": [f"boss-team:{profile.name}"]},
        "agent": {
            "version": "current",
            "idleTimeoutSeconds": 300,
        },
    }


def hub_tenant_payloads(*, base_domain: str = "hermes.local") -> list[dict[str, Any]]:
    return [render_hub_tenant_payload(profile, base_domain=base_domain) for profile in BOSS_PROFILES]


def verify_hub_tenants(tenants: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {tenant.get("id"): tenant for tenant in tenants}
    missing = []
    mismatches = []
    for profile in BOSS_PROFILES:
        tenant = by_id.get(profile.hub_tenant_id)
        if not tenant:
            missing.append(profile.hub_tenant_id)
            continue
        display = tenant.get("displayName", "")
        if profile.name not in display:
            mismatches.append(f"{profile.hub_tenant_id}: displayName does not include {profile.name!r}")
    return {
        "ok": not missing and not mismatches,
        "expected": [profile.hub_tenant_id for profile in BOSS_PROFILES],
        "missing": missing,
        "mismatches": mismatches,
    }
