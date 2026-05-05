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
    BossProfile("hr", "hr_profile", "routing", "llm", "Hires E2B remote teams and manages lifecycle."),
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
    "team_blueprints",
    "wiki",
    "sources",
    "skills",
)

HUB_TENANT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
REPO_ROOT = Path(__file__).resolve().parents[1]
TEAM_DOCS_DIR = REPO_ROOT / "docs" / "team"

TOP_TIER_DOC_SECTIONS: dict[str, tuple[str, str]] = {
    "boss": ("03_top_tier_souls.md", "## ROLE: "),
    "supervisor": ("03_top_tier_souls.md", "## ROLE: "),
    "hr": ("03_top_tier_souls.md", "## ROLE: "),
    "conductor": ("03_top_tier_souls.md", "## ROLE: "),
}

REMOTE_BLUEPRINT_SECTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("growth", "specialist", "04_specialist_souls.md", "## ROLE: "),
    ("eng", "specialist", "04_specialist_souls.md", "## ROLE: "),
    ("brand", "specialist", "04_specialist_souls.md", "## ROLE: "),
    ("room-engine", "execution", "05_team_souls.md", "## TEAM: "),
    ("video", "execution", "05_team_souls.md", "## TEAM: "),
    ("distro", "execution", "05_team_souls.md", "## TEAM: "),
    ("sermons", "execution", "05_team_souls.md", "## TEAM: "),
    ("creators", "execution", "05_team_souls.md", "## TEAM: "),
    ("dev", "execution", "05_team_souls.md", "## TEAM: "),
    ("churches", "execution", "05_team_souls.md", "## TEAM: "),
)

REMOTE_TEAM_BOUNDARY = """## Hermes Harness Deployment Boundary

This deployment adapts the original docs/team operating model to Hermes Harness:
- The hub machine runs only the six local boss-team profiles: boss, supervisor, hr, conductor, critic, and a2a-bridge.
- Only boss is user-facing. All other local profiles are internal.
- Specialist and execution roles from docs/team are not local Hermes profiles on the hub machine.
- hr hires those roles from factory/team_blueprints into factory/teams/<name>/ and executes them on E2B machines.
- The hub keeps local state, assignments, transport metadata, status, artifacts, and audit trails. Remote teams do their active work in E2B.
- Use Codex OAuth through provider openai-codex. Do not configure OpenRouter keys or direct OpenAI API keys.
- Where the source docs say "14 profiles" or "profile create", read that as "six local boss profiles plus remote E2B teams created by harness.tools.spawn_team".
"""

HR_REMOTE_SPAWN_COMMAND = (
    "python3 -m harness.tools.spawn_team --factory /factory --substrate e2b "
    "--template multi-agent --blueprint <team> <team>"
)

FACTORY_TEXT_FILES: dict[str, str] = {
    "QUIET_HOURS.md": """quiet_hours_local:
  start: "23:00"
  end:   "07:00"
timezone: "Asia/Taipei"
batch_reminder_hours: 3
morning_digest_at: "07:30"
""",
    "BLACKBOARD.md": "# BLACKBOARD.md\n\nAppend-only cross-team scratch.\n",
    "PRIORITIZE.md": "# PRIORITIZE.md\n\nFounder overrides go here.\n",
    "activity.log": "",
    "BRAND_VOICE.md": "# BRAND_VOICE.md\n\nPending generation by brand remote team.\n",
    "MESSAGE_FRAMEWORK.md": "# MESSAGE_FRAMEWORK.md\n\nPending generation by brand remote team.\n",
    "CAMPAIGNS_ACTIVE.md": "# CAMPAIGNS_ACTIVE.md\n\nPending generation by brand remote team.\n",
    "POSITIONING.md": "# POSITIONING.md\n\nPending generation by brand remote team.\n",
    "CONTENT_PILLARS.md": "# CONTENT_PILLARS.md\n\nPending generation by brand remote team.\n",
    "CALENDAR.md": "# CALENDAR.md\n\nPending generation by brand remote team.\n",
    "DIRECTIVES.md": "# DIRECTIVES.md\n\nLegacy file. Boss orders go in orders/.\n",
    "PERFORMANCE.md": "# PERFORMANCE.md\n\nPending generation by growth remote team.\n",
}

WIKI_SCHEMA = """# Karpathy Wiki Schema (Layer 3)

Layer 1 factory/sources/: immutable raw source material. Append, never edit.
Layer 2 factory/wiki/: curated synthesis. Mutable through wiki skills.
Layer 3 this file: rules. Only command line edits via decision.

Promotion: a fact graduates from MEMORY.md to wiki when:
1. Referenced 3+ times across sessions, OR
2. Boss explicitly promotes it, OR
3. A skill returns structured output with promote: true.

Cross-refs: Obsidian-style [[wikilinks]]. Indexer regenerates INDEX.md on every wiki write.

Frontmatter for every wiki page:
---
title: ...
type: pastor | creator | church | conference | campaign | audience | competitor | voice | opportunity | lesson | runbook
created_by: <profile-or-team>
created_at: <ISO8601>
updated_at: <ISO8601>
sources: [<paths under factory/sources/>]
confidence: low | medium | high
review_status: draft | reviewed | promoted
---

Not in wiki: drafts, transient status, orders, raw performance snapshots, or private credentials.
"""

WIKI_INDEX = """# Hermes Harness Wiki Index

Auto-regenerated by wiki-index-regen on wiki writes.

## Sections
- [[audience/]]
- [[voice/]]
- [[competitive/]]
- [[pastors/]]
- [[creators/]]
- [[churches/]]
- [[conferences/]]
- [[opportunities/]]
- [[campaigns/]]
- [[lessons/]]
- [[skills-library/]]
- [[branding/]]
- [[runbooks/]]
- [[feature_pipeline/]]
- [[memory-promotions/]]
- [[team_roster/]]
"""

WIKI_SKILLS: dict[str, str] = {
    "wiki-write": """# wiki-write
Write or update a wiki page per factory/wiki/SCHEMA.md.

Steps:
1. Read SCHEMA.md.
2. Determine target path under factory/wiki/.
3. If the page exists: read, merge, preserve frontmatter, update timestamp, append change log.
4. If new: write with full frontmatter.
5. Use [[wikilinks]] for cross-refs.
6. Trigger wiki-index-regen.

Output: path and diff.
Refusals: no fabricated content. Mark unverified facts confidence: low. Never delete; deletions go through a decision.
""",
    "wiki-index-regen": """# wiki-index-regen
Regenerate factory/wiki/INDEX.md.

Steps:
1. Walk factory/wiki/ recursively, skipping .obsidian and .templates.
2. Per directory: count pages and last-updated time.
3. Per page: extract title, type, review_status from frontmatter.
4. Identify missing frontmatter, broken [[wikilinks]], and pages without sources.
5. Write INDEX.md.
""",
    "promote-to-wiki": """# promote-to-wiki
Promote a MEMORY.md fact to a wiki page.

When: 3+ cross-session refs, boss promotion, or skill output with promote: true.

Steps:
1. Read MEMORY.md and identify the fact.
2. Determine target wiki section per SCHEMA.md.
3. Write to factory/wiki/<section>/<slug>.md with frontmatter.
4. Add cross-refs to related pages.
5. Append to factory/wiki/memory-promotions/<date>.md.
""",
    "contradiction-detector": """# contradiction-detector
Scan factory/wiki/ for contradictions.

Steps:
1. For each pair of cross-referenced pages, extract assertions.
2. Identify direct and soft contradictions.
3. Write findings to factory/wiki/INDEX.md#issues.
4. High-confidence contradiction creates a decision-class escalation.
""",
    "source-ingest": """# source-ingest
Process raw input from factory/sources/inbound/ into relevant wiki pages.

Steps:
1. Read raw input.
2. Classify: pastor, creator, church, competitive, trend, transcript, or manual.
3. Extract structured facts.
4. Per fact: create wiki page, append to existing wiki page, or keep in MEMORY.md.
5. Write with sources: [<inbound path>] frontmatter.
6. Move processed input to factory/sources/<category>/.
""",
}


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


def _read_team_doc(filename: str) -> str:
    path = TEAM_DOCS_DIR / filename
    return path.read_text(encoding="utf-8")


def _extract_section(filename: str, marker_prefix: str, name: str) -> str:
    text = _read_team_doc(filename)
    lines = text.splitlines()
    marker = f"{marker_prefix}{name}"
    collecting = False
    selected: list[str] = []
    for line in lines:
        if line.startswith(marker_prefix):
            if collecting:
                break
            if line.strip() == marker:
                collecting = True
                continue
        elif line.startswith("## ") and collecting:
            break
        if collecting:
            selected.append(line)
    body = "\n".join(selected).strip()
    if not body:
        raise ValueError(f"missing section {marker!r} in {filename}")
    return body + "\n"


def _factory_doc(filename: str, *, heading: str) -> str:
    source = _read_team_doc(filename)
    return (
        f"# {heading}\n\n"
        f"Source: docs/team/{filename}\n\n"
        f"{REMOTE_TEAM_BOUNDARY}\n"
        "The source text below is preserved as the operating contract. Any instruction "
        "to create or operate specialist/execution local profiles is superseded by the "
        "E2B remote-team boundary above.\n\n"
        "---\n\n"
        f"{source}"
    )


def _brief_from_section(section: str, name: str) -> str:
    paragraphs = [part.strip() for part in section.split("\n\n") if part.strip()]
    if not paragraphs:
        return f"{name} remote team."
    return "\n\n".join(paragraphs[:2])


def _render_blueprint_yaml(name: str, kind: str, source_file: str, marker_prefix: str) -> str:
    marker_kind = "ROLE" if "ROLE" in marker_prefix else "TEAM"
    return (
        f"name: {name}\n"
        f"kind: {kind}\n"
        "substrate: e2b\n"
        "template: multi-agent-team\n"
        f"source_file: docs/team/{source_file}\n"
        f"source_marker: \"## {marker_kind}: {name}\"\n"
        f"spawn_command: \"{HR_REMOTE_SPAWN_COMMAND.replace('<team>', name)}\"\n"
        "inputs:\n"
        "  - factory assignments copied to factory/teams/<name>/inbox/\n"
        "  - factory/wiki curated memory\n"
        "  - factory/sources immutable raw material\n"
        "outputs:\n"
        "  - factory/teams/<name>/outbox/ artifacts\n"
        "  - factory/teams/<name>/status.json heartbeats\n"
        "approval_gates:\n"
        "  - factory/HARD_RULES.md\n"
        "  - factory/STANDING_APPROVALS.md\n"
        "budget_caps:\n"
        "  - factory/HARD_RULES.md §1\n"
    )


def _render_blueprint_agents(name: str) -> str:
    return (
        f"# AGENTS.md for remote team blueprint {name}\n\n"
        "This is a hireable remote team blueprint, not a hub-machine Hermes profile.\n\n"
        "When hr hires this team:\n"
        f"1. Create state under `/factory/teams/{name}/`.\n"
        "2. Execute active work on an E2B machine.\n"
        "3. Communicate with the boss team through A2A and the factory bridge.\n"
        "4. Keep status, assignments, transport metadata, and artifacts on the hub factory.\n"
        "5. Use Codex OAuth through provider `openai-codex`; do not use OpenRouter or direct OpenAI API keys.\n\n"
        "Read at remote-team boot:\n"
        "- TEAM_SOUL.md\n"
        "- brief.md\n"
        "- criteria.md\n"
        "- context/hiring_blueprint.md, if present in the hired team folder\n"
        "- /factory/PROTOCOL.md\n"
        "- /factory/HARD_RULES.md\n"
        "- /factory/STANDING_APPROVALS.md\n"
        "- /factory/wiki/SCHEMA.md\n"
    )


def _render_blueprint_markdown(name: str, kind: str, source_file: str, marker_prefix: str) -> str:
    section = _extract_section(source_file, marker_prefix, name)
    return (
        f"# {name} Remote Team Blueprint\n\n"
        f"Kind: {kind}\n"
        f"Source: docs/team/{source_file} `{marker_prefix}{name}`\n"
        "Substrate: E2B\n"
        "Base template: multi-agent-team\n\n"
        f"{REMOTE_TEAM_BOUNDARY}\n"
        f"## Spawn\n\n```bash\n{HR_REMOTE_SPAWN_COMMAND.replace('<team>', name)}\n```\n\n"
        "## Source Soul\n\n"
        f"{section}"
    )


def _write_blueprints(factory_dir: Path, *, overwrite: bool) -> None:
    root = factory_dir / "team_blueprints"
    for name, kind, source_file, marker_prefix in REMOTE_BLUEPRINT_SECTIONS:
        section = _extract_section(source_file, marker_prefix, name)
        blueprint = _render_blueprint_markdown(name, kind, source_file, marker_prefix)
        _write_text(root / f"{name}.md", blueprint, overwrite)
        team_root = root / name
        _write_text(team_root / "blueprint.yaml", _render_blueprint_yaml(name, kind, source_file, marker_prefix), overwrite)
        _write_text(team_root / "brief.md", f"# {name} Brief\n\n{_brief_from_section(section, name)}\n", overwrite)
        _write_text(team_root / "TEAM_SOUL.md", f"# {name} TEAM_SOUL\n\n{REMOTE_TEAM_BOUNDARY}\n## Source Soul\n\n{section}", overwrite)
        _write_text(team_root / "criteria.md", f"# {name} Criteria\n\nComplete assigned work, report artifacts through A2A, and obey the source hard rules below.\n\n{section}", overwrite)
        _write_text(team_root / "AGENTS.md", _render_blueprint_agents(name), overwrite)
        if name == "room-engine":
            _write_text(
                team_root / "skills" / "room-concept-generator" / "SKILL.md",
                "# room-concept-generator\n\nGenerate room concepts using the concept envelope from TEAM_SOUL.md.\n",
                overwrite,
            )


def _write_wiki_scaffold(factory_dir: Path, *, overwrite: bool) -> None:
    sources = factory_dir / "sources"
    wiki = factory_dir / "wiki"
    source_dirs = (
        "pastors",
        "corpus",
        "platforms",
        "transcripts",
        "public",
        "inbound",
        "manual_uploads",
    )
    wiki_dirs = (
        "audience",
        "voice",
        "competitive",
        "pastors",
        "creators",
        "churches",
        "conferences",
        "opportunities",
        "campaigns",
        "lessons",
        "skills-library",
        "branding",
        "runbooks",
        "feature_pipeline",
        "memory-promotions",
        "team_roster",
    )
    for dirname in source_dirs:
        (sources / dirname).mkdir(parents=True, exist_ok=True)
    for dirname in wiki_dirs:
        (wiki / dirname).mkdir(parents=True, exist_ok=True)
    _write_text(
        sources / "_IMMUTABLE.md",
        "# IMMUTABLE - Layer 1\n\nAppend, never edit. Corrections use `_corr_<original>.md` sidecars.\n",
        overwrite,
    )
    _write_text(wiki / "SCHEMA.md", WIKI_SCHEMA, overwrite)
    _write_text(wiki / "INDEX.md", WIKI_INDEX, overwrite)
    _write_text(
        wiki / ".obsidian" / "app.json",
        '{"alwaysUpdateLinks": true, "newLinkFormat": "shortest", "useMarkdownLinks": false, "showInlineTitle": true, "showFrontmatter": true, "useTab": false, "tabSize": 2}\n',
        overwrite,
    )
    _write_text(
        wiki / ".obsidian" / "core-plugins.json",
        '["file-explorer","global-search","switcher","graph","backlink","outgoing-link","tag-pane","page-preview","templates","outline","word-count","bookmarks"]\n',
        overwrite,
    )
    _write_text(wiki / ".obsidian" / "community-plugins.json", '["dataview","templater-obsidian"]\n', overwrite)
    _write_text(
        wiki / ".templates" / "pastor.md",
        """---
title: <% tp.file.title %>
type: pastor
created_at: <% tp.date.now("YYYY-MM-DDTHH:mm:ssZ") %>
sources: []
confidence: medium
review_status: draft
clip_auth: false
---

# <% tp.file.title %>

## Identity
- Church:
- Denomination:
- Location:
- Languages:

## Reach
- Followers:
- Audience size:
- Primary platforms:

## Content
- Sermon archive URL:
- Podcast URL:
- Recent themes:

## Notes
""",
        overwrite,
    )
    _write_text(
        wiki / ".templates" / "creator.md",
        """---
title: <% tp.file.title %>
type: creator
created_at: <% tp.date.now("YYYY-MM-DDTHH:mm:ssZ") %>
sources: []
confidence: medium
review_status: draft
funnel_state: prospected
---

# <% tp.file.title %>

## Identity
- Niche:
- Platforms:
- Followers:

## Audience

## Outreach
- Status:
- Last contact:
- Next step:
""",
        overwrite,
    )
    _write_text(
        wiki / ".templates" / "church.md",
        """---
title: <% tp.file.title %>
type: church
created_by: churches
created_at: <% tp.date.now("YYYY-MM-DDTHH:mm:ssZ") %>
sources: []
confidence: medium
review_status: draft
hub_status: prebuilt
---

# <% tp.file.title %>

## Public info
- Denomination:
- Location:
- Service times:
- Website:
- Sermon RSS:

## Hub status
- Pre-built:
- Notified:
- Claimed:
- Customized:

## Bots configured
- ContentBot:
- GreeterBot:
- DiscussionBot:
- PrayerBot:
""",
        overwrite,
    )
    for skill_name, body in WIKI_SKILLS.items():
        _write_text(factory_dir / "skills" / skill_name / "SKILL.md", body, overwrite)
        _write_text(wiki / "skills" / skill_name / "SKILL.md", body, overwrite)


def _write_factory_contract(factory_dir: Path, *, overwrite: bool) -> None:
    docs = {
        "PROTOCOL.md": _factory_doc("06_protocol.md", heading="PROTOCOL.md"),
        "HARD_RULES.md": _factory_doc("HARD_RULES.md", heading="HARD_RULES.md"),
        "STANDING_APPROVALS.md": _factory_doc("STANDING_APPROVALS.md", heading="STANDING_APPROVALS.md"),
    }
    for rel, content in docs.items():
        _write_text(factory_dir / rel, content, overwrite)
    for rel, content in FACTORY_TEXT_FILES.items():
        _write_text(factory_dir / rel, content, overwrite)
    for dirname in ("emails", "social", "pitches", "room_concepts", "videos", "paid_spend"):
        (factory_dir / "drafts" / dirname).mkdir(parents=True, exist_ok=True)
        (factory_dir / "approvals" / dirname).mkdir(parents=True, exist_ok=True)
    _write_wiki_scaffold(factory_dir, overwrite=overwrite)
    _write_blueprints(factory_dir, overwrite=overwrite)


def _write_profile_skills(home_dir: Path, *, overwrite: bool) -> None:
    for skill_name, body in WIKI_SKILLS.items():
        _write_text(home_dir / "skills" / skill_name / "SKILL.md", body, overwrite)


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
        f"8. {factory_dir}/wiki/SCHEMA.md\n\n"
        f"Factory: {factory_dir}\n"
        f"Remote team blueprints: {factory_dir}/team_blueprints\n"
        f"Remote team instances: {factory_dir}/teams\n"
        f"Profile: {profile.name}\n"
        f"Role: {profile.role}\n"
        f"Runtime: {profile.runtime}\n"
        "\n"
        "Architecture rule: do not create specialist/execution Hermes profiles on the hub machine. "
        "Only hr hires those teams under factory/teams/<name>/ and executes them on E2B.\n"
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
            "Your job: form strategy, write orders, coordinate internal boss-team roles, "
            "and presents their work to the external user.\n"
            "When a user asks who you are, how many people are in your team, or what your team "
            "does, answer as the Hermes Harness boss-team coordinator. Do not say you are just "
            "one assistant in chat.\n"
            "The boss team has exactly six profiles: boss, supervisor, hr, conductor, critic, "
            "and a2a-bridge. Only boss is user-facing; supervisor, hr, conductor, critic, and "
            "a2a-bridge are internal roles behind the local factory bus.\n"
            "Specialist and execution teams from docs/team are not local hub profiles. They are "
            "hireable E2B remote teams under factory/team_blueprints, created by hr under "
            "factory/teams when a signed order requires them.\n"
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
    body += "\n" + REMOTE_TEAM_BOUNDARY
    if profile.name == "boss":
        body += (
            "\n"
            "User-facing identity rule: for direct A2A chat, boss speaks for the boss team. "
            "If asked about team size, say there are six boss-team profiles and name them. "
            "Clarify that only boss is exposed to the user; the other profiles coordinate "
            "internally through the factory bus.\n"
        )
    if profile.name == "hr":
        body += (
            "\n"
            "Remote hiring command:\n\n"
            f"```bash\n{HR_REMOTE_SPAWN_COMMAND}\n```\n\n"
            "Use a concrete blueprint name such as `creators`, `dev`, or `growth` in place of `<team>`. "
            "The resulting hired team folder is local state; the execution substrate is E2B.\n"
        )
    if profile.name in TOP_TIER_DOC_SECTIONS:
        filename, marker_prefix = TOP_TIER_DOC_SECTIONS[profile.name]
        body += (
            "\n## Source Operating Soul\n\n"
            f"Adapted from docs/team/{filename} `{marker_prefix}{profile.name}`. "
            "The E2B remote-team boundary above overrides any legacy instruction to create "
            "additional local profiles or tmux sessions.\n\n"
            f"{_extract_section(filename, marker_prefix, profile.name)}"
        )
    elif profile.name == "critic":
        body += (
            "\n"
            "Critic reviews outputs before boss accepts them. Focus on protocol compliance, "
            "hard-rule violations, missing acceptance criteria, stale assumptions, and whether "
            "remote-team artifacts actually answer the order.\n"
        )
    elif profile.name == "a2a-bridge":
        body += (
            "\n"
            "a2a-bridge is a daemon profile. It moves assignments and artifacts between "
            "factory/teams/<name>/ and remote A2A runtimes. It does not invent strategy.\n"
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
    _write_factory_contract(factory_dir, overwrite=overwrite)
    for profile in BOSS_PROFILES:
        (factory_dir / "inbox" / profile.name).mkdir(parents=True, exist_ok=True)
        (factory_dir / "outbox" / profile.name).mkdir(parents=True, exist_ok=True)
    bundles = [
        write_profile_bundle(profile, factory_dir, home_root, overwrite=overwrite)
        if layout == "legacy"
        else write_profile_bundle(profile, factory_dir, home_root, overwrite=overwrite, layout=layout)
        for profile in BOSS_PROFILES
    ]
    for profile in BOSS_PROFILES:
        _write_profile_skills(profile_home(home_root, profile, layout=layout), overwrite=overwrite)
    return {"factory": str(factory_dir), "profiles": profile_names(), "layout": layout, "bundles": bundles}


def verify_local_boss_team(factory_dir: Path, home_root: Path, *, layout: str = "legacy") -> dict[str, Any]:
    missing: list[str] = []
    mismatches: list[str] = []
    for dirname in FACTORY_DIRS:
        if not (factory_dir / dirname).is_dir():
            missing.append(f"factory/{dirname}")
    for filename in ("PROTOCOL.md", "HARD_RULES.md", "STANDING_APPROVALS.md", "QUIET_HOURS.md", "BLACKBOARD.md"):
        if not (factory_dir / filename).is_file():
            missing.append(str(factory_dir / filename))
    for filename in ("SCHEMA.md", "INDEX.md"):
        if not (factory_dir / "wiki" / filename).is_file():
            missing.append(str(factory_dir / "wiki" / filename))
    if not (factory_dir / "sources" / "_IMMUTABLE.md").is_file():
        missing.append(str(factory_dir / "sources" / "_IMMUTABLE.md"))
    for name, _kind, _source_file, _marker_prefix in REMOTE_BLUEPRINT_SECTIONS:
        if not (factory_dir / "team_blueprints" / f"{name}.md").is_file():
            missing.append(str(factory_dir / "team_blueprints" / f"{name}.md"))
        if not (factory_dir / "team_blueprints" / name / "TEAM_SOUL.md").is_file():
            missing.append(str(factory_dir / "team_blueprints" / name / "TEAM_SOUL.md"))
    for profile in BOSS_PROFILES:
        home_dir = profile_home(home_root, profile, layout=layout)
        for filename in ("AGENTS.md", "config.yaml", "SOUL.md", "TEAM_SOUL.md"):
            path = home_dir / filename
            if not path.is_file():
                missing.append(str(path))
        if profile.runtime == "llm" and not (home_dir / "skills" / "wiki-write" / "SKILL.md").is_file():
            missing.append(str(home_dir / "skills" / "wiki-write" / "SKILL.md"))
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
        if soul.exists() and profile.name == "hr":
            text = soul.read_text(encoding="utf-8")
            if "--substrate e2b" not in text or "team_blueprints" not in text:
                mismatches.append(f"{soul}: missing E2B remote-team hiring boundary")
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
