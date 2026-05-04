# INSTALL_GUIDE.md — Dummy Walkthrough

**Read this front to back. Don't skip steps.**

---

## What you're about to install

A 14-profile autonomous marketing factory for Jesuscord. After install:
- 14 AI agents run continuously on your machine
- They communicate via files in a shared `factory/` directory
- A "boss" agent forms strategy and writes orders
- A "supervisor" agent approves orders matching pre-authorized classes (acts as you while you sleep)
- An "hr" agent routes work to teams and keeps profiles healthy
- A "conductor" agent tunes the cron schedule
- 3 specialists (growth/eng/brand) feed strategic info up
- 7 execution teams produce drafts and content
- You receive Telegram digests + tap-approve novel-class items
- Wiki populates in Obsidian as the factory learns

You spend 30-90 min/day on approvals once it's running. Day 1 is more (setting up standing approvals).

---

## Part A — Prerequisites (one-time, ~30 min)

### A.1 Operating system

WSL2 + Ubuntu 22.04+ on Windows 10/11.

PowerShell as Administrator:
```powershell
wsl --install -d Ubuntu-22.04
```

Restart Windows. Open Ubuntu from Start menu. Set username + password.

**Everything from here happens in the Ubuntu terminal.**

### A.2 System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y tmux jq git curl build-essential python3-pip openssl
```

### A.3 Node.js

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version
```

Should print `v20.x.x`.

### A.4 Hermes Agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

Verify:
```bash
hermes --version
```

If "command not found":
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
hermes --version
```

### A.5 Telegram bot

1. Open Telegram (mobile or desktop)
2. Search `@BotFather`, message it
3. Send `/newbot`
4. Pick a name: e.g. "Jesuscord Factory"
5. Pick a username ending in `bot`: e.g. `jesuscord_factory_bot`
6. **BotFather replies with a token** (`1234567890:ABCD-...`). Copy this.
7. In Telegram, **create a new private channel or group**. Name it "Jesuscord Factory".
8. Add your bot to that group (`Add member` → search bot username → add as **admin**)
9. In the group, send `/start@your_bot_username`
10. **Get the chat ID:** open in browser:
    ```
    https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
    ```
    Find `"chat":{"id":-100xxxxxxxxxx,...`. Copy the `-100xxxxxxxxxx` number.

You now have:
- `TELEGRAM_BOT_TOKEN` (the token from step 6)
- `TELEGRAM_CHAT_ID` (the `-100xxx` from step 10)

### A.6 OpenRouter API key

1. Go to https://openrouter.ai
2. Sign up
3. Add credits — start with **$50** (covers first 2-3 days of testing)
4. Settings → Keys → "Create Key" → name it "Jesuscord factory" → copy

### A.7 Optional but helpful

- **Anthropic API key** (https://console.anthropic.com) — direct, often cheaper than OpenRouter for Claude models
- **OpenAI API key** (https://platform.openai.com) — fallback
- **Obsidian** for Windows (https://obsidian.md) — install on the Windows side, NOT in WSL
- **GitHub account** — for megaprompts day 2+
- **Claude Code:**
    ```bash
    npm install -g @anthropic-ai/claude-code
    ```

---

## Part B — Drop the bundle (5 min)

### B.1 Get the bundle into WSL

You have a zip file `jesuscord_factory.zip` (or 17 individual files).

Easiest path — put the zip in your Windows desktop, then:
```bash
cd ~
mkdir -p jesuscord_factory_bundle
cd jesuscord_factory_bundle
cp /mnt/c/Users/$(whoami)/Desktop/jesuscord_factory.zip .
unzip jesuscord_factory.zip
ls
```

You should see 17 files:
```
INSTALL_GUIDE.md
HUMAN_GUIDE.md
00_OVERVIEW.md
01_install.sh
02_SOUL_MASTER.md
03_top_tier_souls.md
04_specialist_souls.md
05_team_souls.md
06_protocol.md
07_wiki_setup.sh
08_cron.md
09_megaprompts.md
11_handoff_and_first_hour.md
HARD_RULES.md
STANDING_APPROVALS.md
yolo_bridge.sh
README.md (optional)
```

### B.2 Make scripts executable

```bash
chmod +x ~/jesuscord_factory_bundle/*.sh
```

### B.3 Extract the cron registration script

The cron registration commands live inside `08_cron.md`. Extract to a runnable script:

```bash
cd ~/jesuscord_factory_bundle
awk '/^```bash$/,/^```$/' 08_cron.md | grep -v '^```' > 08_install_cron.sh
chmod +x 08_install_cron.sh
head -20 08_install_cron.sh   # sanity check
```

You should see the `register()` function and a string of `register boss ...` lines.

---

## Part C — Install (10 min)

### C.1 Set environment variables

**Replace `your-windows-username` with your actual Windows username** (the one you'd see in `C:\Users\your-windows-username\`):

```bash
export WORKSPACE=/mnt/c/Users/your-windows-username/Desktop/JESUSCORD
export OBSIDIAN_VAULT=/mnt/c/Users/your-windows-username/Documents/Obsidian/Jesuscord

export TELEGRAM_BOT_TOKEN="1234567890:ABCD..."
export TELEGRAM_CHAT_ID="-1001234567890"
export OPENROUTER_API_KEY="sk-or-v1-..."

# Optional
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
```

To make these persistent across terminal sessions, append all the same `export` lines to `~/.bashrc`:
```bash
nano ~/.bashrc
# paste the export lines at the bottom
# Ctrl-O, Enter, Ctrl-X to save and exit
source ~/.bashrc
```

### C.2 Run the main installer

```bash
cd ~/jesuscord_factory_bundle
bash 01_install.sh
```

Takes 5-10 minutes. You'll see step-by-step progress:
```
=== JESUSCORD FACTORY INSTALL ===
[OK] hermes: ...
[OK] credentials present
[OK] tmux + jq present
=== STEP 1: Filesystem bus ===
[OK] bus at /mnt/c/Users/.../Desktop/JESUSCORD/factory
...
=== STEP 11: Boot ===
[OK] hermes-boss booted (--yolo)
[OK] hermes-supervisor booted (--yolo)
... (14 total)

============================================================
JESUSCORD FACTORY v2.0 DEPLOY COMPLETE
============================================================
  Profiles: 14 / 14
  Tmux sessions: 15 alive
```

If you see errors, see Part F (troubleshooting).

### C.3 Run wiki setup

```bash
bash 07_wiki_setup.sh
```

Takes ~1 minute. Sets up the 3-layer Karpathy wiki structure, configures Obsidian, installs 5 wiki maintenance skills across all 14 profiles.

### C.4 Register cron jobs

```bash
bash 08_install_cron.sh
```

Takes 1-2 minutes. Registers ~70 cron jobs across the 14 profiles.

If `01_install.sh` already ran this (it tries), you'll see "[SKIP]" or duplicates which is fine — Hermes is idempotent on cron name.

### C.5 Open Obsidian (Windows side)

1. Open Obsidian on Windows (NOT in WSL)
2. "Open folder as vault"
3. Navigate to `Documents\Obsidian\Jesuscord`
4. Open it
5. When Obsidian asks about community plugins: **"Trust author and enable plugins"**
6. Settings (gear icon) → Community plugins → Browse:
   - Search "Dataview" → Install → Enable
   - Search "Templater" → Install → Enable
7. Close Obsidian for now (you'll come back as it populates)

### C.6 Verify everything is alive

```bash
# 15 tmux sessions (14 profiles + 1 gateway)?
tmux ls

# Profile statuses + heartbeats
bash yolo_bridge.sh status

# Live activity log
tail -f $WORKSPACE/factory/activity.log
# Press Ctrl-C to stop watching

# Cron jobs registered for one profile (sanity check)
HERMES_HOME=~/.hermes-boss hermes cron list
```

You should see all 14 profiles alive, heartbeats updating every few minutes, activity log scrolling.

### C.7 Wait ~60 minutes for first Telegram digest

At the next top-of-the-hour boundary, you'll receive in your Telegram channel:

```
🟢 JESUSCORD FACTORY — HOURLY [HH:MM UTC]
PROFILES:    14/14 alive
DRAFTS:      ~250 waiting your tap
ESCALATIONS: 0 need decision
LAST HOUR:
  • room-engine:  ~70 rooms drafted
  • video:        ~22 videos rendered
  • distro:       ~30 social posts queued, 100 emails drafted
  • ...
ORDERS: 8 written by boss, 8 signed by supervisor
HARD_RULES: clean
```

If you don't get this within 70 minutes, see Part F.

---

## Part D — First-day operation

This is what you do during hour 1 to set up the factory for the long run.

### D.1 Hour 1 — set standing approvals (the most important step)

When the first hourly digest arrives, you'll likely see 1-3 approval batches awaiting your tap. They'll be classes like:

- "Approve email batch: 50 personalized pastor pitches"
- "Approve social batch: 20 posts to seed accounts"
- "Approve creator outreach: 5 first-time creator pitches"

**For each one you tap-approve**, the supervisor will follow up:

> "First approval for class `email_drafts_to_pastors_in_seed_list`. Add as standing approval so future instances run without tap? Reply YES, NO, or YES-WITH-LIMIT 500/24h."

**Reply YES for any class you'll be approving repeatedly.**

This is what kills the "click through everything" problem. Every YES adds an entry to `factory/STANDING_APPROVALS.md`. From that point on, supervisor signs orders matching that class without bothering you.

After ~5-7 YES replies during hour 1, the factory is on autopilot for almost everything. Subsequent batches only hit Telegram for genuinely novel classes.

### D.2 Hours 2-12

- New batches arrive on Telegram, but most match standing approvals → no tap needed
- Hourly digests every top-of-hour
- You skim digests; tap any genuinely novel batches
- Optional: skim blackboard occasionally
  ```bash
  tail -100 $WORKSPACE/factory/BLACKBOARD.md
  ```

### D.3 Hours 12-24

- First daily-PM digest at 18:30 UTC (or the time you set in `factory/QUIET_HOURS.md`)
- Comprehensive summary of the day
- First strategic memo from boss in `factory/decisions/strategic_<date>.md`
- First growth memo from growth in `wiki/lessons/growth_<date>.md`
- Read these — they're the high-level "what learned" of the day

### D.4 Sleep mode

When you cross into your defined `quiet_hours` (default `23:00`-`07:00` Asia/Taipei — adjust in `factory/QUIET_HOURS.md`):

- Novel escalations queue silently
- Supervisor keeps signing in-envelope orders
- Boss keeps writing orders
- Teams keep executing

When you wake up (at `morning_digest_at`, default 07:30):
- One comprehensive Telegram message: overnight summary + batch of all queued novel items
- You tap through them in 5-10 minutes
- Day continues

### D.5 Customize quiet hours to your sleep schedule

Edit `factory/QUIET_HOURS.md`:
```bash
nano $WORKSPACE/factory/QUIET_HOURS.md
```

```yaml
quiet_hours_local:
  start: "00:00"      # when you go to bed (local time)
  end:   "08:00"      # when you wake up
timezone: "America/Los_Angeles"   # your timezone
batch_reminder_hours: 3
morning_digest_at: "08:00"
```

Save. Supervisor reads on next cycle.

---

## Part E — Day 2+ (optional megaprompts)

Run these only after the factory has been operating cleanly for 24-48h and you're comfortable with the rhythm.

### E.1 Fork Hermes

GitHub → https://github.com/NousResearch/hermes-agent → click **Fork** (top right). Now you have `https://github.com/<your-handle>/hermes-agent`.

### E.2 Clone fork

```bash
cd ~
git clone https://github.com/<your-handle>/hermes-agent.git hermes-fork
cd hermes-fork
```

### E.3 Open Claude Code

```bash
claude
```

(If `claude` not found: `npm install -g @anthropic-ai/claude-code`)

### E.4 Run megaprompt 09 (lax approval policy)

1. Open `~/jesuscord_factory_bundle/09_megaprompts.md`
2. Find `### THE PROMPT` under `## MEGAPROMPT 09`
3. Copy everything between the triple backticks
4. Paste into Claude Code
5. Claude Code runs the audit (step 1) and **stops**, shows `approval_audit.md`
6. Review the audit — does the scan look sane?
7. Tell Claude Code: `looks good, continue with steps 2-7`
8. Claude Code patches, tests, opens a PR

### E.5 Run megaprompt 10 (AI-time pacing)

Same flow with `## MEGAPROMPT 10` section. Can run in parallel branch.

### E.6 Merge both PRs to your fork's main

GitHub → your fork → Pull Requests → review → Merge.

### E.7 Switch profiles to your fork + factory mode

```bash
# Reinstall hermes from your fork into each profile
for p in boss supervisor hr conductor growth eng brand room-engine video distro sermons creators dev churches; do
  HERMES_HOME=~/.hermes-$p pip install --upgrade -e \
    "git+https://github.com/<your-handle>/hermes-agent.git@main"
done

# Switch from --yolo to factory mode (precise approval policy active)
bash ~/jesuscord_factory_bundle/yolo_bridge.sh off
```

After this:
- Internal work runs without Hermes UI prompts (factory mode = approval_policy.mode=factory)
- Outbound public-surface still gets supervisor signature verification
- Cron tick interval drops to 5s (much crisper schedule resolution)
- Subagent fan-out raises to 25 (more parallelism per profile)
- Throughput meaningfully steps up

---

## Part F — Troubleshooting

### F.1 Install script fails

Most common: missing env var. The script tells you which one.

If `tmux` errors: `sudo apt install -y tmux`
If `jq` errors: `sudo apt install -y jq`
If `hermes: command not found`: see A.4
If profiles fail to create: check `hermes profile list` — names may have collided. Delete with `hermes profile delete <name>` and re-run.

### F.2 No Telegram digest arriving

```bash
# Gateway alive?
tmux attach -t hermes-gateway
# Press Ctrl-b then d to detach (don't close session)

# Bot token correct?
cat ~/.hermes-supervisor/.env

# Test bot manually
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d "chat_id=$TELEGRAM_CHAT_ID&text=test from factory"

# Cron running?
HERMES_HOME=~/.hermes-boss hermes cron list
HERMES_HOME=~/.hermes-boss hermes cron status

# Force-fire the digest
HERMES_HOME=~/.hermes-boss hermes cron run hourly-digest
```

If curl test fails: bot not added to chat as admin OR wrong chat ID OR wrong token.
If curl works but cron doesn't fire: gateway not running. Restart:
```bash
tmux kill-session -t hermes-gateway
tmux new-session -d -s hermes-gateway "HERMES_HOME=~/.hermes-supervisor hermes gateway run"
```

### F.3 A profile is stale

Auto-restart is hr's job (every 5 min cron). Manual:
```bash
tmux kill-session -t hermes-<name>
bash yolo_bridge.sh on  # respawns all that aren't running
```

### F.4 Profile asking approval on every operation

You're not in `--yolo` mode (or the bridge died). Run:
```bash
bash yolo_bridge.sh on
```

### F.5 Profile asking approval on a class you keep approving

It's not in standing approvals yet. Three fixes:

**Fastest — wait for supervisor's prompt:** when you next tap-approve, supervisor follows up "Add as standing?" — reply YES.

**Direct via PRIORITIZE.md:**
```bash
cat >> $WORKSPACE/factory/PRIORITIZE.md <<'EOF'

## STANDING_APPROVAL <class-name>
Scope: <plain English description>
EOF
```
Supervisor processes on next 5-min cycle.

**Edit STANDING_APPROVALS.md directly:**
```bash
nano $WORKSPACE/factory/STANDING_APPROVALS.md
# add a new entry, save
```

### F.6 Budget burning fast

```bash
cat $WORKSPACE/factory/status/hr.narrative.md
```

Lower a cap (HARD_RULES.md is read-only by default):
```bash
chmod +w $WORKSPACE/factory/HARD_RULES.md
nano $WORKSPACE/factory/HARD_RULES.md   # edit §1 caps
chmod 444 $WORKSPACE/factory/HARD_RULES.md
```

Or halt one team:
```bash
touch $WORKSPACE/factory/HALT_<profile>.flag
# resume:
rm $WORKSPACE/factory/HALT_<profile>.flag
```

### F.7 Emergency stop everything

```bash
touch $WORKSPACE/factory/EMERGENCY_HALT.flag
```

All 14 profiles halt within 60s. Resume:
```bash
rm $WORKSPACE/factory/EMERGENCY_HALT.flag
```

### F.8 Read what each profile is doing

```bash
# Activity firehose
tail -f $WORKSPACE/factory/activity.log

# Per-profile recent log
HERMES_HOME=~/.hermes-boss hermes logs -n 100

# Recent decisions
ls -lt $WORKSPACE/factory/decisions/ | head -20

# Pending escalations
ls $WORKSPACE/factory/escalations/

# Drafts queue
ls -la $WORKSPACE/factory/drafts/*/
```

---

## Quick reference card

```bash
# === Install ===
bash 01_install.sh
bash 07_wiki_setup.sh
bash 08_install_cron.sh

# === Status ===
bash yolo_bridge.sh status
tmux ls
tail -f $WORKSPACE/factory/activity.log

# === Standing approvals ===
echo '
## STANDING_APPROVAL <class>
Scope: <description>' >> $WORKSPACE/factory/PRIORITIZE.md

echo '
## REVOKE <class>' >> $WORKSPACE/factory/PRIORITIZE.md

# === Halt ===
touch $WORKSPACE/factory/HALT_<profile>.flag       # one team
rm $WORKSPACE/factory/HALT_<profile>.flag          # resume
touch $WORKSPACE/factory/EMERGENCY_HALT.flag       # all
rm $WORKSPACE/factory/EMERGENCY_HALT.flag

# === Edit hard rules ===
chmod +w $WORKSPACE/factory/HARD_RULES.md
nano $WORKSPACE/factory/HARD_RULES.md
chmod 444 $WORKSPACE/factory/HARD_RULES.md

# === Customize quiet hours ===
nano $WORKSPACE/factory/QUIET_HOURS.md

# === Restart ===
tmux kill-session -t hermes-<name>
bash yolo_bridge.sh on

# === Logs ===
HERMES_HOME=~/.hermes-boss hermes logs -n 100

# === After megaprompts 09 + 10 applied to your fork ===
bash yolo_bridge.sh off
```

---

## What's next

Read **HUMAN_GUIDE.md**. It explains how to operate the team day-to-day, how to think about each role, how to manage them like real people, and creative ways to use them. That's the part that turns a working install into a working organization.
