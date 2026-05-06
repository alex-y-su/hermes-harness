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


@dataclass(frozen=True)
class RemoteBlueprint:
    name: str
    kind: str
    summary: str
    responsibilities: tuple[str, ...]
    outputs: tuple[str, ...]
    acceptance: tuple[str, ...]


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

REMOTE_BLUEPRINTS: tuple[RemoteBlueprint, ...] = (
    RemoteBlueprint(
        name="growth",
        kind="specialist",
        summary="Find, design, and evaluate growth experiments for the active business goal.",
        responsibilities=(
            "Turn the active business goal into measurable acquisition, activation, retention, and revenue hypotheses.",
            "Create experiment tickets with success metrics, kill criteria, instrumentation needs, and review dates.",
            "Read performance artifacts and recommend which plays to double, revise, or stop.",
        ),
        outputs=(
            "experiment briefs",
            "performance reviews",
            "growth backlog updates",
        ),
        acceptance=(
            "Every proposal states the target audience, metric, expected lift, and stop condition.",
            "Claims are grounded in source material or marked as assumptions.",
            "Any public launch, paid spend, external outreach, or credential use is escalated before execution.",
        ),
    ),
    RemoteBlueprint(
        name="eng",
        kind="specialist",
        summary="Own technical architecture, integration plans, reliability, and implementation review.",
        responsibilities=(
            "Assess technical feasibility and implementation risk for product and automation work.",
            "Produce scoped technical plans, validation steps, and rollout notes.",
            "Review shipped artifacts for regressions, missing tests, security issues, and operational risk.",
        ),
        outputs=(
            "technical plans",
            "review findings",
            "verification reports",
        ),
        acceptance=(
            "Plans name the affected systems, write scope, risks, and verification commands.",
            "Reviews lead with concrete bugs or blockers and cite artifact paths.",
            "Risky access, production mutation, or credential use is escalated before execution.",
        ),
    ),
    RemoteBlueprint(
        name="brand",
        kind="specialist",
        summary="Develop positioning, messaging, creative angles, and communication quality for the active domain.",
        responsibilities=(
            "Maintain voice, message framework, competitive positioning, and content principles.",
            "Produce creative angles and copy variants tied to specific audiences and channels.",
            "Review external-facing artifacts for clarity, differentiation, and domain fit.",
        ),
        outputs=(
            "positioning briefs",
            "message frameworks",
            "copy and creative reviews",
        ),
        acceptance=(
            "Messaging names the audience, situation, promise, proof, and channel.",
            "External claims are supportable from source material or clearly marked for validation.",
            "Public posting or direct outreach is escalated before execution unless covered by standing approval.",
        ),
    ),
    RemoteBlueprint(
        name="dev",
        kind="execution",
        summary="Implement scoped product, automation, content, or tooling changes requested by approved tickets.",
        responsibilities=(
            "Convert accepted specs into small implementation tasks with clear verification.",
            "Make scoped changes in the assigned workspace and preserve unrelated user edits.",
            "Return artifacts, diffs, test results, and unresolved blockers to the boss team.",
        ),
        outputs=(
            "patches",
            "implementation notes",
            "test and rollout evidence",
        ),
        acceptance=(
            "Work is limited to the assigned scope and includes verification evidence.",
            "External deployment or production mutation is escalated before execution.",
            "Unresolved blockers are recorded as execution-board blocker tickets, not hidden in prose.",
        ),
    ),
    RemoteBlueprint(
        name="research",
        kind="specialist",
        summary="Gather, verify, and synthesize domain, market, customer, and competitor context.",
        responsibilities=(
            "Ingest approved sources and produce sourced domain intelligence.",
            "Separate facts, assumptions, opinions, and unknowns.",
            "Promote reusable knowledge into the wiki with source paths and confidence levels.",
        ),
        outputs=(
            "research briefs",
            "source summaries",
            "wiki updates",
        ),
        acceptance=(
            "Every factual claim has a source or an explicit confidence marker.",
            "Research includes implications and recommended next tickets when useful.",
            "Private, paid, or credentialed sources are accessed only after approval.",
        ),
    ),
    RemoteBlueprint(
        name="ops",
        kind="execution",
        summary="Maintain cadence, schedules, project hygiene, and cross-team throughput.",
        responsibilities=(
            "Track schedules, stale tickets, blocked work, and handoffs across active teams.",
            "Prepare daily and weekly operating summaries for the boss team.",
            "Surface process bottlenecks and propose system-level improvements through artifacts.",
        ),
        outputs=(
            "schedule reviews",
            "status reports",
            "throughput improvement tickets",
        ),
        acceptance=(
            "Reports distinguish completed work, blocked work, and next actions.",
            "Aging or blocked work is linked to execution-board tickets.",
            "Process changes that alter approvals, access, or production behavior are escalated.",
        ),
    ),
)

REMOTE_TEAM_BOUNDARY = """## Hermes Harness Deployment Boundary

This deployment uses Hermes Harness as a domain-neutral orchestration layer:
- The hub machine runs only the six local boss-team profiles: boss, supervisor, hr, conductor, critic, and a2a-bridge.
- Only boss is user-facing. All other local profiles are internal.
- Specialist and execution roles are hireable blueprints, not local Hermes profiles on the hub machine.
- hr hires those roles from factory/team_blueprints into factory/teams/<name>/ and executes them on isolated remote machines.
- The hub keeps local state, assignments, transport metadata, status, artifacts, and audit trails. Remote teams do their active work in E2B.
- Use Codex OAuth through provider openai-codex. Do not configure OpenRouter keys or direct OpenAI API keys.
- Domain-specific product goals, audiences, channels, and content rules belong in deployment config, orders, team briefs, skills, and wiki pages.
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
    "RESOURCE_REGISTRY.md": """# RESOURCE_REGISTRY.md

Resources are tracked as files under `factory/resources/`.

Every ticket that touches an external account, website, repository, database, app config, paid channel, credentialed API, production environment, or user-visible surface must reference resource IDs in ticket metadata.

Resource files may be JSON or Markdown with frontmatter. Minimal fields:

```json
{
  "id": "website/main",
  "title": "Main website",
  "kind": "website",
  "state": "ready",
  "owner": "dev",
  "approval_policy": "production mutations require explicit approval",
  "access": "repo and deployment credentials required"
}
```

Allowed states: `ready`, `missing`, `needs-access`, `needs-setup`, `blocked`, `deprecated`.
""",
}

GENERIC_PROTOCOL = f"""# PROTOCOL.md

{REMOTE_TEAM_BOUNDARY}

## Operating Loop
- Boss is the only user-facing profile and speaks for the boss team.
- Internal profiles coordinate through factory files, execution-board tickets, schedules, and A2A updates.
- Work should be represented as bounded tickets with owner, scope, acceptance criteria, and review evidence.
- Blocked work stays visible as a blocker ticket while unrelated work continues.
- Remote teams must write status and artifacts back under factory/teams/<name>/.
- Critic reviews meaningful deliverables before boss treats them as complete.

## Approval Flow
- In-envelope internal planning, research synthesis, local draft creation, and local code review can proceed without user interruption.
- External outreach, public publication, paid spend, production mutation, credential use, irreversible data changes, or legal/compliance-sensitive actions require standing approval or explicit user approval.
- Before requesting approval, verify required resources in `factory/resources/` exist and are in a usable state. If a resource is missing or needs access/setup, create a resource setup/access ticket first.
- Approval requests should be concrete decision packets: requested action, target resources, reason, artifact/diff/content, expected impact, blast radius, cost, preconditions checked, expiry, rollback/fallback, and what happens if denied.
- Ticket metadata should include `resources` or `resource_dependencies` with resource IDs.
"""

GENERIC_HARD_RULES = """# HARD_RULES.md

## Universal Guardrails
- Never expose secrets in logs, tickets, artifacts, or chat.
- Never use credentials, mutate production, contact external parties, publish content, or spend money unless covered by standing approval or explicit user approval.
- Never invent facts. Mark assumptions and confidence levels.
- Never hide blockers. Create or update blocker tickets with the exact missing input or approval.
- Never let one blocked ticket stop unrelated active work.
- Never create broad write scopes when a small scoped task is enough.
- Never request approval for a production/public/paid/credentialed action until the target resource exists in `factory/resources/` and the approval explains exactly what will happen and why.
- Preserve unrelated user changes in any workspace.

## Remote Execution
- Remote teams work in isolated workspaces and receive only the context needed for their assignment.
- Remote teams return artifacts, status, verification evidence, and blockers through the factory bus.
- Remote teams do not read unrelated system directories or shared secrets unless the assignment explicitly grants that context.
"""

GENERIC_STANDING_APPROVALS = """# STANDING_APPROVALS.md

No domain-specific standing approvals are granted by the generic harness template.

Deployments may add project-specific standing approvals here. Each approval should include:
- class
- allowed action
- limits
- expiry or review cadence
- owner
- audit path

Absent a matching standing approval, external publication, outreach, credential use, paid spend, production mutation, and irreversible data changes must escalate to the user.
"""

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
type: domain | customer | account | partner | campaign | audience | competitor | voice | opportunity | lesson | runbook | experiment | artifact
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
- [[domains/]]
- [[customers/]]
- [[partners/]]
- [[opportunities/]]
- [[campaigns/]]
- [[experiments/]]
- [[metrics/]]
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
2. Classify: domain, customer, account, partner, campaign, audience, competitor, trend, artifact, or manual.
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


def _yaml_list(values: tuple[str, ...], *, indent: str = "  ") -> str:
    return "".join(f"{indent}- {value}\n" for value in values)


def _markdown_list(values: tuple[str, ...]) -> str:
    return "".join(f"- {value}\n" for value in values)


def _render_blueprint_yaml(blueprint: RemoteBlueprint) -> str:
    name = blueprint.name
    return (
        f"name: {name}\n"
        f"kind: {blueprint.kind}\n"
        "substrate: e2b\n"
        "template: multi-agent-team\n"
        f"summary: {blueprint.summary}\n"
        f"spawn_command: \"{HR_REMOTE_SPAWN_COMMAND.replace('<team>', name)}\"\n"
        "responsibilities:\n"
        f"{_yaml_list(blueprint.responsibilities)}"
        "inputs:\n"
        "  - factory assignments copied to factory/teams/<name>/inbox/\n"
        "  - factory/wiki curated memory\n"
        "  - factory/sources immutable raw material\n"
        "outputs:\n"
        f"{_yaml_list(blueprint.outputs)}"
        "  - factory/teams/<name>/outbox/ artifacts\n"
        "  - factory/teams/<name>/status.json heartbeat\n"
        "acceptance:\n"
        f"{_yaml_list(blueprint.acceptance)}"
        "approval_gates:\n"
        "  - factory/HARD_RULES.md\n"
        "  - factory/STANDING_APPROVALS.md\n"
        "budget_caps:\n"
        "  - factory/HARD_RULES.md\n"
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


def _render_blueprint_markdown(blueprint: RemoteBlueprint) -> str:
    name = blueprint.name
    return (
        f"# {name} Remote Team Blueprint\n\n"
        f"Kind: {blueprint.kind}\n"
        "Substrate: E2B\n"
        "Base template: multi-agent-team\n\n"
        f"{blueprint.summary}\n\n"
        f"{REMOTE_TEAM_BOUNDARY}\n"
        f"## Spawn\n\n```bash\n{HR_REMOTE_SPAWN_COMMAND.replace('<team>', name)}\n```\n\n"
        "## Responsibilities\n\n"
        f"{_markdown_list(blueprint.responsibilities)}\n"
        "## Outputs\n\n"
        f"{_markdown_list(blueprint.outputs)}\n"
        "## Acceptance\n\n"
        f"{_markdown_list(blueprint.acceptance)}"
    )


def _write_blueprints(factory_dir: Path, *, overwrite: bool) -> None:
    root = factory_dir / "team_blueprints"
    for blueprint in REMOTE_BLUEPRINTS:
        name = blueprint.name
        markdown = _render_blueprint_markdown(blueprint)
        _write_text(root / f"{name}.md", markdown, overwrite)
        team_root = root / name
        _write_text(team_root / "blueprint.yaml", _render_blueprint_yaml(blueprint), overwrite)
        _write_text(team_root / "brief.md", f"# {name} Brief\n\n{blueprint.summary}\n", overwrite)
        _write_text(
            team_root / "TEAM_SOUL.md",
            (
                f"# {name} TEAM_SOUL\n\n"
                f"{REMOTE_TEAM_BOUNDARY}\n"
                f"## Mission\n\n{blueprint.summary}\n\n"
                f"## Responsibilities\n\n{_markdown_list(blueprint.responsibilities)}\n"
                f"## Outputs\n\n{_markdown_list(blueprint.outputs)}\n"
                f"## Acceptance\n\n{_markdown_list(blueprint.acceptance)}"
            ),
            overwrite,
        )
        _write_text(
            team_root / "criteria.md",
            (
                f"# {name} Criteria\n\n"
                "Complete assigned work, report artifacts through A2A, and obey the factory hard rules.\n\n"
                f"{_markdown_list(blueprint.acceptance)}"
            ),
            overwrite,
        )
        _write_text(team_root / "AGENTS.md", _render_blueprint_agents(name), overwrite)


def _write_wiki_scaffold(factory_dir: Path, *, overwrite: bool) -> None:
    sources = factory_dir / "sources"
    wiki = factory_dir / "wiki"
    source_dirs = (
        "raw",
        "public",
        "research",
        "telemetry",
        "inbound",
        "manual_uploads",
    )
    wiki_dirs = (
        "audience",
        "voice",
        "competitive",
        "domains",
        "customers",
        "partners",
        "opportunities",
        "campaigns",
        "experiments",
        "metrics",
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
        wiki / ".templates" / "domain.md",
        """---
title: <% tp.file.title %>
type: domain
created_at: <% tp.date.now("YYYY-MM-DDTHH:mm:ssZ") %>
sources: []
confidence: medium
review_status: draft
---

# <% tp.file.title %>

## Context
- Market:
- Audience:
- Product:
- Geography:

## Useful Facts

## Open Questions
""",
        overwrite,
    )
    _write_text(
        wiki / ".templates" / "customer.md",
        """---
title: <% tp.file.title %>
type: customer
created_at: <% tp.date.now("YYYY-MM-DDTHH:mm:ssZ") %>
sources: []
confidence: medium
review_status: draft
---

# <% tp.file.title %>

## Segment
- Need:
- Current alternative:
- Trigger:

## Evidence

## Implications
""",
        overwrite,
    )
    _write_text(
        wiki / ".templates" / "experiment.md",
        """---
title: <% tp.file.title %>
type: experiment
created_at: <% tp.date.now("YYYY-MM-DDTHH:mm:ssZ") %>
sources: []
confidence: medium
review_status: draft
status: proposed
---

# <% tp.file.title %>

## Hypothesis

## Audience

## Metric
- Success:
- Kill:

## Results
""",
        overwrite,
    )
    for skill_name, body in WIKI_SKILLS.items():
        _write_text(factory_dir / "skills" / skill_name / "SKILL.md", body, overwrite)
        _write_text(wiki / "skills" / skill_name / "SKILL.md", body, overwrite)


def _write_factory_contract(factory_dir: Path, *, overwrite: bool) -> None:
    docs = {
        "PROTOCOL.md": GENERIC_PROTOCOL,
        "HARD_RULES.md": GENERIC_HARD_RULES,
        "STANDING_APPROVALS.md": GENERIC_STANDING_APPROVALS,
    }
    for rel, content in docs.items():
        _write_text(factory_dir / rel, content, overwrite)
    for rel, content in FACTORY_TEXT_FILES.items():
        _write_text(factory_dir / rel, content, overwrite)
    (factory_dir / "resources").mkdir(parents=True, exist_ok=True)
    for dirname in ("messages", "publications", "experiments", "product_specs", "patches", "spend_requests"):
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
            "Specialist and execution teams are not local hub profiles. They are "
            "hireable remote teams under factory/team_blueprints, created by hr under "
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
            "Use a concrete blueprint name such as `research`, `dev`, or `growth` in place of `<team>`. "
            "The resulting hired team folder is local state; the execution substrate is E2B.\n"
        )
    if profile.name == "critic":
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
    for blueprint in REMOTE_BLUEPRINTS:
        name = blueprint.name
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
