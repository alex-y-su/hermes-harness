# Implementation Plan v2 — Hermes-Driven Orchestration + Repo Cleanup

Three fixes folded in: external-asset awareness (Phase 2), media-blueprint + delegation heuristic (Phase 2), creative capacity (new Phase 3.5).

## Executive summary

- **Tool registration is via Hermes Skills** (`SKILL.md` + `execute.sh`), already used by `harness/skills/post-twitter-real/` and `grant-access/`. No MCP, no `tools:` config block. Adding a tool = adding a skill folder.
- **The pulse playbook moves from doc to prompt**: `docs/cards/operator-pulse-prompt.md` Steps A–G get rendered into boss `AGENTS.md` via `harness/boss_team.py:render_agents`.
- **Single canonical catalog**: new `harness/skills_catalog.py` declares all tool-skills with `allowed_profiles`. `_write_profile_skills` (boss_team.py:804) iterates it.
- **`orchestrator.py` shrinks 513 → ~120 lines** (safety-net only). Stale-detect / retry / user-request / waiting-marker logic moves to conductor cron skills.
- **Cutover is shadow-gated**: 24h side-by-side via `HARNESS_SHADOW_MODE=1` writing to `factory/decisions/_shadow/`. Promote at <5% divergence.
- **External-asset manifest** added: `factory/external-assets.json` + `list_external_assets` tool. Hermes can answer *"what surfaces do I control?"* before proposing any external action.
- **`media` blueprint added** as the 7th hireable team — handles video/image/audio/heavy-compute work.
- **Delegation heuristic** explicit in boss AGENTS.md: 5-trigger rule for when to dispatch vs. inline.
- **Phase 3.5 (new) — Creative capacity**: replaces structural diversity gate with semantic similarity, adds Step E.2 ideation pulse, adds creative-bet examples to boss SOUL, reserves a "taste" section in `MEMORY.md`.
- **Cleanup deletes ~14 files** (8 tmp_*, 4 stale docs, 2 post-migration); `.gitignore` gets `tmp_*.py/md/json` block.
- **Total budget: ~260 agent-iterations** across 8 phases.

## The 8 phases

| Phase | Goal | Iter |
|---|---|---|
| **0** | Pre-flight — confirm skill-registration mechanism, inventory leftovers, decompose `orchestrator.py` | 5 |
| **1** | Tool-registration scaffold — `harness/skills_catalog.py`, `harness/skills_render.py`, modify `_write_profile_skills` | 25 |
| **2** | E2B tools + external-asset manifest + media blueprint + delegation heuristic | 45 |
| **3** | Task tools — board ops, atomic writes, literal-form pre-pass, pulse playbook → boss AGENTS.md | 50 |
| **3.5** | Creative capacity — semantic novelty gate, Step E.2 ideation, taste memory, inline generation | 30 |
| **4** | Cron migration — conductor → boss → hr → supervisor → critic. Each runs 24h shadow before promotion. | 60 |
| **5** | Cutover — rename `orchestrator.py` → `safety_watchdog.py`; delete migrated logic | 20 |
| **6** | Cleanup — delete tmp_* files, archive stale docs, .gitignore guard | 10 |
| **7** | Docs refresh — README, boss-team-contract.md, 01-247-recipe.md, new external-assets.md and creative-pulse.md | 15 |
| **Total** | | **260** |

---

## Phase 0 — Pre-flight (truths to lock down)

### 0.1 Hermes tool-registration mechanism — confirmed

| Question | Answer | Evidence |
|---|---|---|
| Mechanism | Skills directory with `SKILL.md` (YAML frontmatter) + executable companion (`execute.sh`) | `harness/skills/post-twitter-real/execute.sh`, `harness/skills/grant-access/execute.sh` |
| Per-profile registration | `_write_profile_skills(home_dir, ...)` at `harness/boss_team.py:804`, called from `install_local_boss_team` (`harness/boss_team.py:980-981`) | n/a |
| Cron registration | `hermes cron create --name <n> --schedule <cron> --prompt <p> [--skill <s>]`, exists in `scripts/activate_24_7_root_team.sh:243` | n/a |
| MCP / `tools:` block | **Not used.** No `tools:` key in `render_config` (`harness/boss_team.py:809-831`) | n/a |
| Hooks | `~/.hermes/hooks/` exists but is empty — out of scope | n/a |

### 0.2 Open questions to resolve before Phase 1

1. **Skill discovery cache** — does `hermes cron run` fork fresh (sees newly-installed skills) or share long-lived process needing `hermes reload-skills`?
2. **Skill parameter schema** — does SKILL.md frontmatter support `parameters:` or does Hermes parse prose? Read `hermes_cli/skills.py` at pinned commit `645a2f48`.
3. **Per-profile cron isolation** — does `hermes --profile <p>` resolve crons under `$HERMES_HOME/profiles/<p>/cron/` or `$HERMES_HOME/cron/` keyed by profile?
4. **`run_skill` redundancy** — Hermes invokes skills natively from agent output. Is explicit `run_skill` tool needed? Decision: keep as testable-dispatch fallback.
5. **MEMORY.md sections** — does Hermes' memory loader respect reserved sections (Facts/Taste/Vetoed) or treat as flat? Blocks Phase 3.5d.

### 0.3 Inventory of leftovers

**Untracked tmp_* at repo root** (delete — violates "No .py patch scripts for prompt edits"):
- `tmp_apply_jesuscord_patch.py`
- `tmp_clear_queue_leases.py`
- `tmp_e2b_artifact_path_patch.py`
- `tmp_fix_assignment_state.py`
- `tmp_hard_prune_canceled.py`
- `tmp_mod_disambiguation_patch.py`
- `tmp_ticket_corrected_mod_spec.md`
- `tmp_ticket_website_patch.md`

**Stale / contradicted docs**:
- `docs/team/` (16 files) — pre-approval-flow planning; references legacy `~/.hermes-<profile>` layout
- `docs/practical/24-7-todo.md` — superseded
- `docs/practical/07-hermes-harness-plugin-plan.md` — historical (file says so at line 3)

**Hidden-tool bucket** (no SKILL.md emitted; CLI entrypoints stay):
- `harness/tools/spawn_team.py` (264 lines)
- `harness/tools/run_assignment_sandbox.py` (199 lines)
- `harness/tools/finalize_assignment_sandbox.py` (154 lines)

### 0.4 `orchestrator.py` decomposition (513 lines)

| Function | Lines | Disposition |
|---|---|---|
| `build_parser` / `main` / `run` | 28-49, 490-513 | Keep (CLI shell, safety-net only) |
| `_run_sandbox_lifecycle` | 123-297 | Keep as safety-net (TTL-archive) |
| Stale-assignment detection | 351-405 | → skill `harness-watchdog-stale` |
| Retry-due processing | 317-349 | → skill `harness-watchdog-retry` |
| User-request alerts | 407-441 | → skill `harness-watchdog-user-requests` |
| Waiting-on-user marker | 443-484 | → skill `harness-watchdog-waiting` |

After migration: orchestrator runs every 5 min as safety net, fires only on missed pulses (>10 min stale).

---

## Phase 1 — Tool registration scaffold

**Goal**: one canonical skill wrapper, one place that emits all tool skills into each profile, smoke test that Hermes sees them.

### File-level changes

- **NEW** `harness/skills_catalog.py`:
  ```python
  HARNESS_TOOL_SKILLS: dict[str, ToolSkill] = {
      "list_teams": ToolSkill(
          summary="List remote E2B team blueprints + active hires",
          allowed_profiles={"hr", "boss"},
          frontmatter={...},
          executor="python3 -m harness.tools.query_remote_teams --json",
          input_schema={...},
      ),
      ...
  }
  ```
- **NEW** `harness/skills_render.py` — `render_skill_bundle(skill, profile) -> dict[str,str]` returning `{"SKILL.md": ..., "execute.sh": ...}`. Frontmatter follows `~/.hermes/skills/devops/kanban-orchestrator/SKILL.md` shape.
- **MODIFY** `harness/boss_team.py:_write_profile_skills` (line 804) — replace `WIKI_SKILLS` loop with iteration over `HARNESS_TOOL_SKILLS` filtered by `allowed_profiles`.
- **KEEP** all existing CLI entrypoints in `pyproject.toml:50-60` (skills shell to them).

### Smoke test

`tests/test_skills_catalog.py`:
- Each profile receives the expected subset of skills
- `hermes --profile hr skill list` lists registered tool names

### Rollback

Phase 1 is additive. Delete `harness/skills_catalog.py` import from `boss_team.py` and re-run install — old `WIKI_SKILLS` path still works.

---

## Phase 2 — E2B team tools + external-asset manifest + media blueprint

**Goal**: HR can hire/dispatch/inspect/sunset E2B teams via skills only; never sees E2B SDK paths. Hermes knows what external surfaces exist. New `media` blueprint handles heavy-compute work.

### 2a. E2B team tools (5 exposed, 3 hidden)

| Skill | Wraps | Allowed profiles |
|---|---|---|
| `list_teams` | `harness/tools/query_remote_teams.py` | hr, boss, supervisor |
| `hire_team` | `harness/tools/spawn_team.py` (sanitized args, no `--api-key`) | hr |
| `dispatch_team` | `harness/tools/dispatch_team.py` | hr |
| `inspect_team` | `harness/tools/inspect_team.py` | hr, boss, critic |
| `sunset_team` | `harness/tools/sunset_team.py` | hr |

**Hidden** (no SKILL.md): `spawn_team`, `run_assignment_sandbox`, `finalize_assignment_sandbox`.

### 2b. External-asset manifest (NEW)

- **NEW** `factory/external-assets.json` — declarative, human-curated:
  ```json
  {
    "twitter": [{"handle": "@x0040h", "skill": "post-twitter-real",
                 "approval": "required", "rate_limit_per_day": 5}],
    "email": [{"sender": "alex@fulldive.com", "skill": "send-email",
               "approval": "standing", "domains": ["fulldive.com"]}],
    "domains": [{"host": "fulldive.com", "skill": "publish-page",
                 "approval": "required"}],
    "compute": [{"name": "e2b-sandbox", "blueprint_match": ["media", "eng", "dev"]}]
  }
  ```
- **NEW** tool `list_external_assets` — allowed: `boss, hr, supervisor`. Executor: `python3 -m harness.tools.list_external_assets --json`.
- **MODIFY** boss/hr/supervisor `AGENTS.md`: *"Before proposing any card with kind in {tweet, email, publish, ...}, call `list_external_assets`. If surface isn't listed, escalate — do not assume."*
- **Test gate** `tests/test_external_assets.py`:
  - Empty manifest → tool returns `{}`, boss prompt blocks unknown-surface cards
  - Manifest with one Twitter handle → `propose-tweet` proceeds; second concurrent tweet checks `rate_limit_per_day`

### 2c. Media blueprint + delegation heuristic (NEW)

- **MODIFY** `harness/boss_team.py:REMOTE_BLUEPRINTS` — add 7th entry:
  ```
  media: video / image / audio generation, transcription, heavy-batch compute.
         Sandbox includes ffmpeg, ImageMagick, whisper, comfyui, runway/pika clients.
         Default budget: $20/assignment. Default deliverable: factory/teams/<name>/outbox/.
  ```
- **MODIFY** `render_team_soul` for `hr`: list 7 blueprints.
- **MODIFY** boss `AGENTS.md`: insert delegation heuristic:
  ```
  Delegate to a remote team via hr.dispatch_team when ANY:
    - estimated work > 50 turns
    - requires GPU or large-model inference
    - requires specialized tooling (ffmpeg, blender, headless browser)
    - involves > 5 generated-artifact files
    - wall-clock estimate > 10 minutes
  Default: delegate. Inline work is for orchestration, short-form copy, decisions.
  ```
- **MODIFY** boss `SOUL.md`: add 3rd worked example (video):
  > *"Order: 'we need a 30s teaser video for the prayer-circle launch.' boss → hr orders `hire_team(blueprint=media, name=media-prayer-2026)` → `dispatch_team(media-prayer-2026, {goal: '30s vertical teaser, fulldive brand', success_metric: 'video posted + 100 views in 24h', deadline_utc: 2026-05-12T00:00Z, deliverable_path: factory/teams/media-prayer-2026/outbox/teaser.mp4, max_budget_usd: 20})`"*

### 2d. Prompt content updates

- **MODIFY** `render_team_soul` for `hr` (line 909-916): replace `HR_REMOTE_SPAWN_COMMAND` shell block with prose dispatch contract naming `hire_team`/`dispatch_team` and the blueprint catalog.
- **MODIFY** `render_soul` for boss (line 865-881): two original worked examples + the video example above.

### Test gates

- `test_list_teams_smoke` — hr profile sees `list_teams`; empty factory returns `{"success": true, "teams": []}`
- `test_hire_dispatch_contract` — `hire_team(blueprint=research)` then `dispatch_team` with id; factory bus state matches `factory/teams/research-*/inbox/`
- `test_sunset_idempotent` — `sunset_team` twice returns success+no-op
- `test_hidden_tools_not_exposed` — `spawn_team`/SKILL.md does NOT exist in any profile home
- `test_media_blueprint_hireable` — `hire_team(blueprint=media)` succeeds; sandbox image includes ffmpeg

### Rollback

Drop catalog entries; CLIs unchanged.

---

## Phase 3 — Task system tools

**Goal**: boss can read/write the card board, validate, run skills, all via tools — and execute the full pulse playbook.

### Tools

| Skill | Wraps | Allowed profiles |
|---|---|---|
| `read_board` | thin reader over `factory/board.json` | boss, supervisor, critic |
| `read_card` | reads single card by id | boss, supervisor, critic |
| `read_inbox` | lists `factory/inbox/*.md` excluding `processed/` | boss |
| `add_card` | atomic-rename appends to `board.json` after validation | boss |
| `update_card` | atomic-rename mutation by id | boss |
| `kill_card` | sets `status=killed` + `result.kill_reason` atomically | boss |
| `run_skill` | invokes any registered side-effect skill | boss |
| `validate_card` | wraps `harness/cards/validator.py::validate_card_shape` | boss |

### File-level changes

- **NEW** `harness/tools/board.py` — backs `read_board`, `read_card`, `add_card`, `update_card`, `kill_card`. Every write uses `os.rename` from `tmp_<short-uuid>` next to target.
- **NEW** `harness/tools/inbox.py` — `list_unprocessed`, `process_one(name)`. Preserves literal-form pre-pass logic from `docs/cards/operator-pulse-prompt.md:160-180`.
- **NEW** `harness/tools/inbox_intent.py` — `parse_literal_intents(body) -> list[Intent]` (deterministic; LLM judgment runs only when this returns empty). Preserves commit `31470c3`.
- **NEW** `harness/tools/run_skill.py` — invokes named skill at `harness/skills/<name>/execute.sh`. Whitelists allowed names from `factory/skills/_REGISTRY.json`.
- **MODIFY** `harness/cards/validator.py` — expose `validate_card_shape` under CLI shim with `--json` for machine-parseable error.

### Pulse playbook → boss AGENTS.md

- **MODIFY** `render_agents` (line 834-855): when `profile.name == "boss"`, append verbatim Steps A–G from `docs/cards/operator-pulse-prompt.md`. Substitute filesystem actions with skill names.
- **DELETE** `docs/cards/operator-pulse-prompt.md` after migration. Add redirect `docs/cards/README.md` pointing to `harness/boss_team.py:render_agents`.

### Card schema pin → SOUL.md

- **MODIFY** `render_soul` (boss / critic / conductor): append JSON skeleton from `docs/cards/card-guide.md:7-30`.

### Inbox literal-form preservation

Literal forms (`approve <appr-id>`, `grant <accr-id>`, `creds installed`, etc.) move into `harness/tools/inbox_intent.py` as a regex table.

**Test gate** `tests/test_inbox_intent.py` — exhaustive table-test of every literal form including multi-line and free-form-tail cases.

### Test gates (FAIL_TO_PASS)

- `test_one_pulse_one_step` — two queued cards; one pulse advances exactly one card by one step
- `test_in_flight_priority` — one `doing` + one higher-priority `queued`; pulse picks `doing` (regression for `adc1cbf`)
- `test_diversity_gate` — last 5 done with same signature; refuse 6th matching
- `test_atomicity_under_concurrent_pulse` — kill mid-write; `board.json` is pre or post, never partial
- `test_inbox_literal_form_dispatch` — `"approve appr-..."` recognized at confidence 1.0, no LLM call
- `test_validate_card_rejects_missing_locator` — card with no `outcome.locator_field` exits non-zero

### Rollback

Skills can be removed from catalog; boss falls back to direct file ops via terminal. Pulse playbook in AGENTS.md remains correct either way.

---

## Phase 3.5 — Creative capacity (NEW)

**Goal**: Hermes generates novel proposals; gate refuses *semantic* repeats; "taste" persists across compactions.

### 3.5a. Semantic novelty gate

- **MODIFY** `harness/cards/validator.py` — replace structural diversity gate with:
  - Compute embedding of `card.title + card.input.brief` (use Hermes' configured provider; cache to `factory/_embeddings/<card-id>.json`)
  - Cosine-similarity check against last-N done cards (N=20) and pending approvals
  - Reject when max similarity > 0.85
  - Keep structural check as secondary fallback when embeddings unavailable
- **NEW** tool `check_card_novelty(card)` returns `{novel, max_similarity, nearest_card_id, nearest_title}`. Called by `validate_card`.
- **Test gate** `tests/test_novelty.py` — two cards with identical role+skill but different titles ("Easter campaign" vs "summer hackathon promo") both pass; two with same brief reject the second.

### 3.5b. Step E.2 ideation pulse

- **MODIFY** boss `AGENTS.md` — extend operator pulse:
  ```
  Step E.2 (Ideation, conditional): Trigger when ALL hold:
    - No card is currently 'doing' (queue idle)
    - Current top priority in PRIORITIZE.md hasn't changed in >24h
    - Last ideation pulse was >6h ago (check factory/status/last-ideation.json)
  Action:
    1. Read PRIORITIZE.md, MEMORY.md taste section, last 20 done cards
    2. Generate 3 novel proposals attacking the top priority from different angles
    3. Score each: cost-to-test (1-5), potential observable impact (1-5),
       semantic novelty (1 - max_similarity to existing)
    4. Add the highest-scoring proposal as a draft card via add_card
    5. Write factory/status/last-ideation.json with timestamp + 3 proposals
  At most one ideation card per 6h. Other cards advance normally.
  ```
- **NEW** `factory/status/last-ideation.json` — tracks ideation cadence + audit trail.
- **Test gate** `tests/test_ideation.py` — given idle queue + stale priority, one pulse adds exactly one ideation card; two pulses 1h apart add only one; ideation card has all 3 proposals in audit field.

### 3.5c. Creative-bet examples in boss SOUL

- **MODIFY** boss `SOUL.md` — add "Past bets" section with 3-5 concrete examples:
  - One that worked (with observable that landed)
  - One that flopped (with what we learned)
  - One that surprised (unexpected angle)

These come from the user — cannot be auto-generated. Ship with placeholders + note: *"Phase 3.5 deployment requires user to fill in from real bet history."*

### 3.5d. MEMORY.md taste section

- **MODIFY** `render_soul` for boss — emit `MEMORY.md` template with reserved sections:
  ```markdown
  ## Facts
  (auto-promoted facts about the project, teams, infra)
  
  ## Taste
  (what's worked, what's flopped, what surprised us — manually curated)
  
  ## Vetoed approaches
  (things we tried that don't work; do not retry without new info)
  ```
- "Taste" section read by ideation step. Never auto-written by Hermes — only by user or via `memory_note` skill.
- **NEW** tool `memory_note(section, body, source)` — appends to a section, preserves provenance, enforces section whitelist.
- **Test gate** `tests/test_memory_taste.py` — `memory_note(section="Taste", ...)` appends correctly; `memory_note(section="Schema", ...)` rejects.

### 3.5e. Loosen inline content generation

- **MODIFY** boss `AGENTS.md`: *"Inline generation is preferred over skill-registration for unique one-shot creative output (copy, proposals, drafts). Register a skill only when the operation will be invoked >3 times."*
- **Test gate** `tests/test_inline_generation.py` — pulse with inline-role pipeline generates content into `card.input.draft` without invoking any skill.

---

## Phase 4 — Cron migration per profile

**Goal**: each profile has its cron job(s) registered; conductor migrates first (lowest blast radius), boss next.

### File-level changes

- **NEW** `harness/profiles/<profile>/prompts/<prompt-name>.md` per cron entry. Short trigger referencing AGENTS.md playbook.
  - `harness/profiles/boss/prompts/strategic-pulse.md`: *"Run one operator pulse per the playbook in your AGENTS.md. Stop after one card-step or one inbox message, whichever comes first."*
  - `harness/profiles/conductor/prompts/watchdog.md`: *"Run watchdog: call `harness-watchdog-stale`, `harness-watchdog-retry`, `harness-watchdog-waiting`. Surface findings only — record alerts."*
- **NEW** `scripts/install_profile_crons.sh` — reads `harness/profiles/<profile>/cron.toml` per profile and calls `hermes --profile <p> cron create`.

### Cron registration table

| Profile | Cron | Cadence | Prompt | Skills exposed |
|---|---|---|---|---|
| conductor | `watchdog` | `*/1 * * * *` | `watchdog.md` | watchdog skills, `inspect_team` |
| boss | `strategic-pulse` | `*/5 * * * *` | `strategic-pulse.md` | all task tools, `read_board`, `run_skill`, `list_external_assets` |
| hr | `route-orders` | `*/15 * * * *` | `route-orders.md` | 5 E2B tools, `read_board`, `list_external_assets` |
| supervisor | `sign-orders` | `*/10 * * * *` | `sign-orders.md` | `read_board`, `read_card`, sign-only skills, `list_external_assets` |
| critic | (on-demand) | manual | `critique.md` | `read_card`, `read_board`, `inspect_team` |
| a2a-bridge | (daemon, unchanged) | n/a | n/a | unchanged |

### Migration order

conductor → boss → hr → supervisor → critic. Each is one-commit gate.

### Shadow-run plan

For 24h after registering each profile's cron:
1. Existing Python orchestrator continues at `*/5` (current cadence)
2. New Hermes-driven cron writes decisions to `factory/decisions/_shadow/<profile>/<unix>.json` instead of mutating `board.json` (feature flag `HARNESS_SHADOW_MODE=1`)
3. `tests/test_shadow_diff.py` reads both decision streams, reports divergence
4. **Promote when**: 24h with <5% divergence and zero "different terminal action" cases

### Test gates per profile

- Conductor: 24h shadow shows watchdog skills produce same TTL-archive set as Python orchestrator within ±1 sandbox per cycle
- Boss: shadow pulse picks same card 95%+ of the time; diversity gate fires on identical signatures
- HR: zero spurious `hire_team` calls; manual review of every shadow `hire_team`
- Supervisor: identical sign decisions on replay of last 24h orders

### Rollback

Each profile's cron is independently registered. To revert: `hermes --profile <p> cron delete <name>`. Python orchestrator remains source of truth until promotion.

---

## Phase 5 — Cutover and Python orchestrator retirement

**Goal**: shrink `harness/tools/orchestrator.py` from 513 to ~120 lines.

### What stays

- `_run_sandbox_lifecycle` (lines 123-297) — TTL-archive blocked/orphan sandboxes
- `cleanup_expired_leases` call (line 313)
- New: pulse-watchdog. If `factory/status/last-pulse.json` is older than 10 minutes, write alert.

### What gets deleted

- Stale-assignment detection (lines 351-405) — moved to `harness-watchdog-stale`
- Retry-due processing (lines 317-349) — moved to `harness-watchdog-retry`
- User-request alert escalation (lines 407-441) — moved to `harness-watchdog-user-requests`
- Waiting-on-user marker (lines 443-484) — moved to `harness-watchdog-waiting`

### File-level changes

- **MODIFY** `harness/tools/orchestrator.py` — remove deleted blocks; rename to `harness/tools/safety_watchdog.py`. Update entrypoints in `pyproject.toml:29-30` and systemd unit at `scripts/install_native_systemd.sh:199`. Two CLI names (`harness-orchestrator`, `harness-e2b-watchdog`) preserved as aliases.
- **MODIFY** `harness/tools/run_soak.py:15` — drop import of removed pieces.

### Test gate

`tests/test_safety_watchdog.py::test_only_runs_when_pulse_stale` — given recent `last-pulse.json`, safety watchdog produces no actions (regression: today's orchestrator runs always).

### Rollback

Single revert commit restores deleted functions. Phase 5 is gated on Phase 4's 24h shadow passing.

---

## Phase 6 — Repo cleanup

### Files to delete

```
tmp_apply_jesuscord_patch.py
tmp_clear_queue_leases.py
tmp_e2b_artifact_path_patch.py
tmp_fix_assignment_state.py
tmp_hard_prune_canceled.py
tmp_mod_disambiguation_patch.py
tmp_ticket_corrected_mod_spec.md
tmp_ticket_website_patch.md
docs/practical/24-7-todo.md
docs/cards/operator-pulse-prompt.md   # after Phase 3
```

### Files to relocate

```
docs/team/                                          → docs/_archive/team-2026-04/
docs/practical/07-hermes-harness-plugin-plan.md     → docs/_archive/plugin-plan-2026-04.md
```

### Files to rename

```
harness/tools/orchestrator.py  → safety_watchdog.py
```

### Update `.gitignore`

```
# patch-script debt — never commit one-off mutators
tmp_*.py
tmp_*.md
tmp_*.json
```

### Git history hygiene

One cleanup commit per phase, not interleaved. Order: (1) delete tmp_* (post-Phase 0), (2) Phase 5 orchestrator rename, (3) Phase 6 doc relocation.

### Test gate

`scripts/verify.sh` must pass after every cleanup commit.

---

## Phase 7 — Documentation refresh

### Files to update

- **MODIFY** `docs/boss-team-contract.md` — point at `harness/skills_catalog.py` as canonical tool inventory; replace "orchestrator polls every 5 min" language with "boss runs `strategic-pulse` cron via playbook in `boss/AGENTS.md`."
- **MODIFY** `docs/practical/01-247-recipe.md` — add section pointing at `scripts/install_profile_crons.sh` as canonical installer.
- **MODIFY** `README.md` — *Hermes drives orchestration; harness provides a tool catalog and substrate adapters*.
- **NEW** `CLAUDE.md` — repo-level Claude/agent guidance: pin model, point at `harness/skills_catalog.py`, document verify command, list anti-patterns.
- **NEW** `docs/external-assets.md` — operator guide for editing the manifest, granting/revoking surface access.
- **NEW** `docs/creative-pulse.md` — explains Step E.2, ideation cadence, how to seed `MEMORY.md` taste section.

---

## Cross-cutting concerns

### Single verification command — `scripts/verify.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
exec >/tmp/verify.log 2>&1   # silent on success
ruff check .
pyright || mypy harness harness_remote
pytest -q
python3 -m harness.cards.validator --self-test
python3 -m harness.tools.boss_team verify-local --factory factory --home-root "$HOME/.hermes" --layout hermes-profiles
echo "ok"
```

On failure: `cat /tmp/verify.log >&2; exit 1`. Wired into `make verify`.

### Rollback strategy summary

| Phase | Rollback |
|---|---|
| 1 | Delete `harness/skills_catalog.py` import; old behavior |
| 2 | Drop catalog entries; CLIs unchanged |
| 3 | Drop catalog entries; revert `render_agents` change |
| 3.5 | Revert validator changes; remove ideation block from AGENTS.md |
| 4 | `hermes --profile <p> cron delete <name>` per registered job |
| 5 | Single revert commit on `safety_watchdog.py` |
| 6 | `git revert` cleanup commit |
| 7 | n/a (docs only) |

### What NOT to do (anti-patterns)

- **No `tmp_*.py` patch scripts.** All mutations through skills + atomic writes. Enforced by `.gitignore`.
- **Do not leak E2B paths to Hermes prompts.** HR sees blueprints by name; `hire_team` encapsulates `--api-key`, sandbox template id, region.
- **Do not write `factory/board.json` directly from Hermes.** Every write through `update_card`/`add_card`/`kill_card` with `os.rename`.
- **Do not cut over without 24h shadow.** Phase 5 gated on Phase 4's diff report.
- **No untested cron change.** Every `cron create` paired with fixture-driven test of its prompt against frozen factory state.
- **Do not bundle skills the profile shouldn't have.** `allowed_profiles` in `HARNESS_TOOL_SKILLS` is authority.
- **Do not auto-write `MEMORY.md` taste section.** Only user or `memory_note` skill writes there. Auto-write would launder Hermes' own assumptions back into its taste — a feedback loop.
- **Do not let the ideation step run on every pulse.** The 6h cooldown + queue-idle precondition is load-bearing.
- **Do not assume external surface exists because a skill exists.** Always gate on `list_external_assets` — surfaces can be deauthorized without removing skill code.

---

## Tool catalog (final, 14-15 tools)

| Bucket | Tools |
|---|---|
| Read state | `read_board`, `read_card`, `read_inbox`, `list_teams`, `inspect_team`, `list_external_assets` |
| Mutate work | `add_card`, `update_card`, `kill_card`, `hire_team`, `dispatch_team`, `sunset_team` |
| Validation & dispatch | `validate_card`, `check_card_novelty`, `run_skill`, `memory_note` |

---

## Iteration budget

| Phase | Iter |
|---|---|
| 0 — pre-flight | 5 |
| 1 — scaffold | 25 |
| 2 — E2B + assets + media | 45 |
| 3 — task tools | 50 |
| 3.5 — creative capacity | 30 |
| 4 — cron + shadow | 60 |
| 5 — cutover | 20 |
| 6 — cleanup | 10 |
| 7 — docs | 15 |
| **Total** | **260** |

---

## What user must provide (blocking 3.5c)

Phase 3.5 cannot ship without 3-5 real "past bets" you've made. Auto-generated examples will train the wrong taste. When we hit Phase 3.5, expect a question: *"Give me 3-5 creative bets from the last 6 months — what was the bet, what was the observable result, what surprised you?"*

---

## Critical files for implementation

- `/Users/x0040h/projects/hermes-harness/harness/boss_team.py`
- `/Users/x0040h/projects/hermes-harness/harness/tools/orchestrator.py`
- `/Users/x0040h/projects/hermes-harness/docs/cards/operator-pulse-prompt.md`
- `/Users/x0040h/projects/hermes-harness/harness/cards/validator.py`
- `/Users/x0040h/projects/hermes-harness/scripts/activate_24_7_root_team.sh`
