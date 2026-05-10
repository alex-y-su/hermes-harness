# Hermes Harness — Docs

Research and practical notes accumulated while figuring out how to run [Nous Research's Hermes Agent](https://github.com/NousResearch/hermes-agent) as a 24/7 autonomous worker on long-horizon, complex creative tasks.

Two folders, deliberately separated:

- **`research/`** — what is, with evidence and citations. Read first if you want to understand the landscape; read again later if you forget *why* a recommendation was made.
- **`practical/`** — what to do, with concrete configs, files, and code. Read first if you just want to ship.

Canonical implementation contracts:

- [`boss-team-contract.md`](boss-team-contract.md) — the generic six-profile boss team used by `install.sh`, `harness-boss-team`, and hub verification.

## Reading order

For a fresh read, top-to-bottom:

1. [`research/01-hermes-delegation.md`](research/01-hermes-delegation.md) — what Hermes already ships for sub-task delegation
2. [`research/02-orchestration-projects.md`](research/02-orchestration-projects.md) — Mission Control, Hermes Workspace, Paperclip — what they are, what they actually do for Hermes
3. [`research/03-paperclip-investigation.md`](research/03-paperclip-investigation.md) — Paperclip's stars vs. real engagement, overhead, contributor base
4. [`research/04-multi-vs-single-agent-evidence.md`](research/04-multi-vs-single-agent-evidence.md) — the literature: when multi-agent beats single agent, and when it doesn't (compute-matched)
5. [`research/05-autonomy-forcing-functions.md`](research/05-autonomy-forcing-functions.md) — why multi-personality works for autonomy (and what mechanism is actually doing the work)
6. [`research/06-hermes-247-capabilities.md`](research/06-hermes-247-capabilities.md) — what Hermes already provides for long-horizon autonomy, with file:line citations

Then:

7. [`practical/01-247-recipe.md`](practical/01-247-recipe.md) — the config + SOUL.md + `/goal` recipe
8. [`practical/02-durable-delegation-design.md`](practical/02-durable-delegation-design.md) — design for hours-to-days delegated sub-tasks
9. [`practical/03-forcing-functions-extensions.md`](practical/03-forcing-functions-extensions.md) — the seven single-agent autonomy upgrades, ranked
10. [`practical/04-decision-tree.md`](practical/04-decision-tree.md) — when to pick what

## TL;DR for the impatient

- Hermes already has `delegate_task` (synchronous, in-turn, parallel children, depth-bounded). Durable / multi-day delegation does not exist; the closest existing primitive is the goal loop (`/goal`) + auto-judge.
- Multi-agent vs single-agent on **task quality at matched compute**: single agent equals or wins on cognitively coupled work; multi-agent wins only on parallelizable, I/O-bound, breadth-first tasks.
- Multi-personality role-play **does** extend autonomy time-horizon — but the mechanism is "role-switching resets the RLHF wrap-up bias and inserts a critic," not architectural superiority. The same forcing functions can be added to one agent.
- For 24/7 operation on Hermes: `--yolo` + `goals.max_turns: 1000` + `agent.max_turns: 500` + a SOUL.md that forbids wrap-up + `/goal` with strict judge + cron watchdog. Tokens are not the limiter; goal ambiguity and goal-judge model strength are.
- Real gaps in Hermes today: no Stop / on_turn_end hook, no built-in Reflexion / self-critique pass, no `final_answer` veto. Each is ~150 lines of plugin code.

## Honest caveats

- The "single agent + forcing functions = multi-persona at autonomy" claim is **a mechanism-grounded hypothesis**, not a benchmarked result. Reflexion / Self-Refine / Voyager are evidence in that direction; no head-to-head paper specifically on horizon length.
- The compute-matching critique (Section 4) is well-supported on quality benchmarks but the field has barely measured the autonomy axis. Where the literature is silent, the docs flag it.
- Snapshots like Paperclip's stars and contributor counts are from May 2026 — they will drift.

Date of synthesis: 2026-05-02.
