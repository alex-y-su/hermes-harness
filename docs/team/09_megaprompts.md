# Megaprompts for Claude Code

Two prompts to paste into Claude Code (`claude` CLI) inside your fork of `nousresearch/hermes-agent`. They patch your fork to add: (a) a per-channel approval policy mode, (b) AI-time pacing for batch/cron throughput.

Run AFTER the factory has been operating in `--yolo` bridge mode for 24-48h. Don't run on day 1.

---

## MEGAPROMPT 09 — Lax approval policy

### What it does

Adds `agent.approval_policy.mode` config with three settings: `strict` (current default, unchanged), `factory` (precise per-channel/per-action gates per HARD_RULES.md §3 + STANDING_APPROVALS.md), `yolo` (existing). Also adds signature-checking for `require_signature` actions — supervisor-signed orders verify before execute.

### How to run

1. Fork https://github.com/NousResearch/hermes-agent on GitHub
2. `cd ~ && git clone https://github.com/<your-handle>/hermes-agent.git hermes-fork`
3. `cd hermes-fork && claude` (Claude Code session)
4. Copy the prompt below between the triple backticks
5. Paste into Claude Code
6. Claude Code runs step 1 (audit) and STOPS. Review `approval_audit.md`.
7. Tell Claude Code "continue with steps 2-7"
8. Claude Code patches, tests, opens PR

### THE PROMPT

```
You are working in a local clone of Nous Research's Hermes Agent (MIT licensed) at the current working directory. I'm the operator. I want to patch the default approval/confirmation behavior to match a per-channel gating model defined in my factory's HARD_RULES.md.

GOAL

Hermes currently prompts for approval on a wide range of "dangerous" operations. I want a more precise scope:

UNGATED (no prompt):
- Reading any file
- Writing files inside workspace dirs (factory/, wiki/, sources/, ~/.hermes-*/)
- Spawning subagents
- Calling LLM providers
- Calling MCP servers I've explicitly added
- Running cron jobs I've registered
- Reading inbound messaging
- Writing to drafts/*
- Executing skills
- Updating wiki/, MEMORY.md, USER.md
- Reading public web
- Cross-profile inbox/outbox writes

GATED (still prompts, signature required):
- Sending email/SMS/DM to non-team recipients
- Posting to public social accounts
- Spending above $10
- Submitting to app stores
- Modifying ~/.hermes-supervisor/.factory_human_secret or HARD_RULES.md
- Writing to factory/HARD_RULES.md or factory/EMERGENCY_HALT.flag
- Running shell commands matching dangerous patterns (keep current denylist)
- Writing outside configured workspace dirs

WHAT I NEED YOU TO DO

1. SCAN: Find every approval/confirmation prompt point. Search for: 'approval', 'confirm', 'yolo', 'dangerous', 'prompt(', 'inquirer', 'requireApproval', 'shouldConfirm', 'is_dangerous'. Map each to (a) trigger action (b) current guard (c) UNGATED/GATED bucket. Output to approval_audit.md at repo root.

2. DESIGN: Add agent.approval_policy:
   approval_policy:
     mode: factory | strict | yolo   # default: strict
     ungated_paths: [factory/, wiki/, sources/, ~/.hermes-*/]
     ungated_actions: [llm_call, mcp_call, subagent_spawn, draft_write, wiki_write, web_read, cron_execute, skill_execute, cross_profile_chain]
     gated_actions: [email_send, social_post, paid_spend_above_10, app_store_submit, shell_dangerous]
     gated_paths: [factory/HARD_RULES.md, factory/EMERGENCY_HALT.flag]
     require_signature: [email_send, social_post, paid_spend_above_10]

   When mode==factory: route every approval through policy resolver.
   When mode==strict: unchanged from current main.
   When mode==yolo: current --yolo behavior.
   Keep existing --yolo CLI flag.

3. IMPLEMENT: Create lib/approval_policy.{ts,py} (detect stack). Replace each prompt point with shouldPrompt = approvalPolicy.evaluate(action, path). Path matching: glob patterns. Resolve relative paths against HERMES_HOME.

4. SIGNATURE-CHECKING for require_signature actions:
   - Don't auto-skip prompts.
   - Look for factory/approvals/<id>.resolved with HMAC matching ~/.hermes-supervisor/.factory_human_secret
   - Signature present + verifies → proceed without prompt
   - Absent or fails → fall through to interactive prompt
   - Signature format: HMAC-SHA256(approval_id|choice|timestamp|HUMAN_SECRET)

5. TESTS: Each ungated action no prompt, each gated action prompts unless yolo, signature actions verify, mode switching works, --yolo overrides everything.

6. DOCS: Update docs/user-guide/security.md. Add docs/guides/factory-mode.md.

7. PR: Branch feature/approval-policy-modes. Commit "feat(approval): introduce approval_policy with strict/factory/yolo modes". Open PR with approval_audit.md in body.

CONSTRAINTS

- Do NOT remove --yolo flag, current dangerous-shell denylist, change defaults for non-opt-in users.
- Do NOT break existing tests.
- Surgical patch. Stop after step 1 and show me approval_audit.md before steps 2-7.
- Don't widen scope. Document misfits in approval_audit.md, ask before refactoring.

Read README.md, package.json/pyproject.toml, docs/user-guide/security.md first to understand architecture. Then run step 1.
```

---

## MEGAPROMPT 10 — AI-time pacing

### What it does (honest version)

**This patch CAN do:**
- Remove `await sleep()` patterns existing for UX pacing only
- Parallelize sequential operations where dependency graph allows
- Raise concurrent subagent fan-out cap (default 5 → 25)
- Drop cron tick interval (60s → 5s)
- Remove animation/spinner waits
- Increase HTTP keep-alive and connection pool sizes

**This patch CANNOT do:**
- Make LLMs sample faster (compute-bound at provider)
- Skip provider rate limits (correctness)
- Skip required sequential dependencies (script-then-render)

So: removes artificial slowdown. Not a "speed multiplier."

### How to run

Same flow as 09. Either parallel branch or after 09 merges.

### THE PROMPT

```
You are working in a local clone of Nous Research's Hermes Agent (MIT licensed) at the current working directory. I want to patch artificial pacing for batch/cron operations.

GOAL

Add agent.ai_time_mode config. When enabled, agent removes artificial pacing patterns and runs at maximum throughput within provider rate limits. When disabled (default), unchanged.

WHAT IS ARTIFICIAL PACING

Sleeps, delays, sequential-when-parallel-works that exist for UX reasons not correctness:
- Spinner/animation delays
- "Thinking..." pauses between tool calls
- Sequential tool calls when graph permits parallel
- Conservative polling intervals
- HTTP pool sizes set conservatively
- Subagent fan-out caps set conservatively
- Stream chunking with delays for "natural typing" effect
- Inter-tool retry backoffs longer than rate-limit-required

WHAT I DO NOT WANT YOU TO TOUCH

- Provider rate limits (don't hammer through)
- Retry backoffs handling 429/503 (correctness)
- Sequential operations with genuine data dependencies
- Safety/approval prompts (governed by approval_policy)
- Lock acquisition timeouts (correctness)
- Anything affecting correctness or output quality

STEPS

1. SCAN: Every await sleep, setTimeout, time.sleep, asyncio.sleep, setInterval. Classify (a) UX pacing (b) rate-limit backoff (c) correctness wait (d) polling. Find every for/forEach over async ops that could be Promise.all/asyncio.gather. Find every concurrency cap and pool size with current default. Output to ai_time_audit.md.

2. DESIGN: Add agent.ai_time_mode: bool (default false). When true:
   - UX pacing sleeps: skip
   - Rate-limit backoffs: keep
   - Correctness waits: keep
   - Polling: shorten (cron tick 60s→5s, gateway poll 30s→5s)
   - Sequential async loops over independent ops: gather-parallel
   - Concurrency caps: subagent fan-out 5→25, HTTP pool 10→50, keep-alive on

3. IMPLEMENT: Create lib/ai_time.{ts,py} with:
   - pacingSleep(ms, reason) — skip if reason='ux' and ai_time_mode
   - parallelize(asyncFns, opts) — honors ai_time_mode for concurrency cap
   - pollingInterval(name, defaultMs) — returns factory-tuned value in ai_time_mode
   Replace pacing points with helpers. Annotate original behavior in comments.

4. PROVIDER POOLING: HTTP keep-alive on, pool size configurable. ai_time_mode raises pool to 50. Pre-warm provider connection on profile boot.

5. SUBAGENT FAN-OUT: Find subagent-spawn caps. ai_time_mode raises to 25.

6. CRON SCHEDULER: ai_time_mode drops scheduler tick to 5s.

7. STREAMING: ai_time_mode forces display.streaming=false (saves 50-200ms per response).

8. TESTS: Toggle correctness. Benchmark assertion: ai_time_mode ≥2x faster on fan-out workload.

9. DOCS: docs/guides/ai-time-mode.md. Be honest: "removes artificial pacing, doesn't make models sample faster, multiplier depends on workload."

10. PR: feature/ai-time-mode branch. Commit "feat(agent): add ai_time_mode for batch/cron throughput".

CONSTRAINTS

- Don't remove rate-limit awareness.
- Don't skip provider error handling.
- Don't change defaults for non-opt-in users.
- Conservative on parallelization — leave sequential when correctness uncertain.
- Stop after step 1 and show me ai_time_audit.md.
```

---

## After both PRs merge

```bash
# Reinstall hermes from your fork into each profile
for p in boss supervisor hr conductor growth eng brand room-engine video distro sermons creators dev churches; do
  HERMES_HOME=~/.hermes-$p pip install --upgrade -e \
    "git+https://github.com/<your-handle>/hermes-agent.git@main"
done

# Switch from --yolo to factory mode
bash yolo_bridge.sh off
```

Throughput steps up meaningfully. Internal work runs without prompts. Outbound public-surface still gets supervisor signature verification.
