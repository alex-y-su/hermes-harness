# Jesuscord Factory v2.0 — Bundle Index

14-profile autonomous marketing factory. Goal: 10M Jesuscord installs in 90 days.

Note: this folder is a legacy, domain-specific Jesuscord bundle. It is not the canonical Hermes Harness boss-team contract. The generic Hermes Harness boss team is six profiles (`boss`, `supervisor`, `hr`, `conductor`, `critic`, `a2a-bridge`) and is defined in [`../boss-team-contract.md`](../boss-team-contract.md).

## Read in this order

1. **INSTALL_GUIDE.md** — dummy walkthrough to get it running. Parts A-F.
2. **HUMAN_GUIDE.md** — how to operate the team day-to-day. Read after install.
3. **00_OVERVIEW.md** — architecture diagram + file index, for reference.

## Run in this order

```bash
# Required env vars
export WORKSPACE=/mnt/c/Users/<windows-user>/Desktop/JESUSCORD
export OBSIDIAN_VAULT=/mnt/c/Users/<windows-user>/Documents/Obsidian/Jesuscord
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export OPENROUTER_API_KEY="..."

# Make scripts executable
chmod +x *.sh

# Extract cron registration script from 08_cron.md
awk '/^```bash$/,/^```$/' 08_cron.md | grep -v '^```' > 08_install_cron.sh
chmod +x 08_install_cron.sh

# Run installers
bash 01_install.sh
bash 07_wiki_setup.sh
bash 08_install_cron.sh

# Verify
bash yolo_bridge.sh status
tmux ls
tail -f $WORKSPACE/factory/activity.log
```

## File-by-file

| File | What it is | When to touch |
|---|---|---|
| `INSTALL_GUIDE.md` | Dummy install walkthrough | Read once before installing |
| `HUMAN_GUIDE.md` | Operating manual for the team | Read after install; reference during operation |
| `00_OVERVIEW.md` | Architecture + file index | Reference |
| `01_install.sh` | Main installer — 14 profiles, bus, MCP, Telegram, tmux | Run once |
| `02_SOUL_MASTER.md` | Inherited by every profile | Don't edit unless you know what you're doing |
| `03_top_tier_souls.md` | boss / supervisor / hr / conductor souls | Edit to tune top-tier behavior |
| `04_specialist_souls.md` | growth / eng / brand souls | Edit to tune specialist behavior |
| `05_team_souls.md` | 7 execution team souls | Edit per team |
| `06_protocol.md` | Becomes `factory/PROTOCOL.md` (the bus contract) | Don't edit during run; bumps protocol_version |
| `07_wiki_setup.sh` | Karpathy 3-layer wiki + Obsidian + 5 maintenance skills | Run once |
| `08_cron.md` | Cron schedule reference + register script (extract via awk) | Reference |
| `09_megaprompts.md` | Lax-approval + AI-time megaprompts for Claude Code | Day 2+ optional |
| `11_handoff_and_first_hour.md` | Boot prompt + minute-by-minute hour-1 contract | Reference |
| `HARD_RULES.md` | Immutable constitution — caps, refusals, gates | Edit only after `chmod +w`, then re-`chmod 444` |
| `STANDING_APPROVALS.md` | Class-level pre-authorizations | Writeable; auto-grown by supervisor + you |
| `yolo_bridge.sh` | Switch profiles between --yolo and factory mode | Run after install + after megaprompts |
| `README.md` | This file | — |

## Mental model in three lines

- 14 AI agents form a marketing company.
- You're the founder. They run the work. You set the mission and tap-approve novel classes.
- Read **HUMAN_GUIDE.md**.
