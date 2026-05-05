from __future__ import annotations

import re
from pathlib import Path

from harness import boss_team


def test_canonical_profile_names_are_generic_six() -> None:
    assert boss_team.profile_names() == ["boss", "supervisor", "hr", "conductor", "critic", "a2a-bridge"]
    assert len(boss_team.profile_names()) == 6


def test_install_and_verify_local_boss_team(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    home_root = tmp_path / "home"

    result = boss_team.install_local_boss_team(factory, home_root, overwrite=True)

    assert result["profiles"] == boss_team.profile_names()
    verification = boss_team.verify_local_boss_team(factory, home_root)
    assert verification == {
        "ok": True,
        "profiles": boss_team.profile_names(),
        "layout": "legacy",
        "missing": [],
        "mismatches": [],
    }
    assert (home_root / ".hermes-a2a-bridge" / "config.yaml").read_text(encoding="utf-8").find(
        "runtime: daemon"
    ) != -1
    boss_soul = (home_root / ".hermes-boss" / "SOUL.md").read_text(encoding="utf-8")
    boss_team_soul = (home_root / ".hermes-boss" / "TEAM_SOUL.md").read_text(encoding="utf-8")
    assert "exactly six profiles: boss, supervisor, hr, conductor, critic, and a2a-bridge" in boss_soul
    assert "Do not say you are just one assistant in chat" in boss_soul
    assert "If asked about team size, say there are six boss-team profiles" in boss_team_soul
    assert "Specialist and execution teams from docs/team are not local hub profiles" in boss_soul
    assert "--substrate e2b" in (home_root / ".hermes-hr" / "TEAM_SOUL.md").read_text(encoding="utf-8")
    assert (home_root / ".hermes-boss" / "skills" / "wiki-write" / "SKILL.md").exists()
    assert (factory / "PROTOCOL.md").exists()
    assert (factory / "HARD_RULES.md").exists()
    assert (factory / "STANDING_APPROVALS.md").exists()
    assert (factory / "wiki" / "SCHEMA.md").exists()
    assert (factory / "sources" / "_IMMUTABLE.md").exists()
    assert (factory / "team_blueprints" / "creators.md").exists()
    assert (factory / "team_blueprints" / "creators" / "TEAM_SOUL.md").exists()
    assert "E2B" in (factory / "team_blueprints" / "dev" / "TEAM_SOUL.md").read_text(encoding="utf-8")
    for remote_name in ("growth", "eng", "brand", "room-engine", "video", "distro", "sermons", "creators", "dev", "churches"):
        assert not (home_root / f".hermes-{remote_name}").exists()


def test_install_official_hermes_profile_layout(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    hermes_home = tmp_path / ".hermes"

    boss_team.install_local_boss_team(factory, hermes_home, overwrite=True, layout="hermes-profiles")

    verification = boss_team.verify_local_boss_team(factory, hermes_home, layout="hermes-profiles")
    assert verification["ok"] is True
    assert (hermes_home / "profiles" / "boss" / "AGENTS.md").exists()
    config = (hermes_home / "profiles" / "boss" / "config.yaml").read_text(encoding="utf-8")
    assert "provider: openai-codex" in config
    assert "openrouter" not in config.lower()


def test_verify_local_boss_team_reports_missing_profile(tmp_path: Path) -> None:
    factory = tmp_path / "factory"
    home_root = tmp_path / "home"
    boss_team.install_local_boss_team(factory, home_root, overwrite=True)
    (home_root / ".hermes-critic" / "SOUL.md").unlink()

    verification = boss_team.verify_local_boss_team(factory, home_root)

    assert verification["ok"] is False
    assert str(home_root / ".hermes-critic" / "SOUL.md") in verification["missing"]


def test_hub_tenant_payloads_use_valid_ids() -> None:
    payloads = boss_team.hub_tenant_payloads()
    assert len(payloads) == 6
    by_profile = {payload["displayName"].split(": ", 1)[1]: payload for payload in payloads}

    assert by_profile["hr"]["id"] == "hr_profile"
    assert by_profile["a2a-bridge"]["id"] == "a2a_bridge"
    for payload in payloads:
        assert re.match(r"^[a-z][a-z0-9_]{2,62}$", payload["id"])
        assert payload["browser"] == {"enabled": False}
        assert payload["agent"] == {"version": "current", "idleTimeoutSeconds": 300}
        assert payload["auth"]["jwtSubjects"][0].startswith("boss-team:")


def test_verify_hub_tenants() -> None:
    tenants = [
        {"id": payload["id"], "displayName": payload["displayName"]}
        for payload in boss_team.hub_tenant_payloads()
    ]

    assert boss_team.verify_hub_tenants(tenants)["ok"] is True
    missing = boss_team.verify_hub_tenants(tenants[:-1])
    assert missing["ok"] is False
    assert missing["missing"] == ["a2a_bridge"]
