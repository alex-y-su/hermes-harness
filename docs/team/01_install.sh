#!/usr/bin/env bash
# 01_install.sh — Jesuscord Factory installer (14 profiles)

set -euo pipefail

# ============================================================
# CONFIG
# ============================================================

WORKSPACE="${WORKSPACE:-/mnt/c/Users/$(whoami)/Desktop/JESUSCORD}"
OBSIDIAN_VAULT="${OBSIDIAN_VAULT:-/mnt/c/Users/$(whoami)/Documents/Obsidian/Jesuscord}"
FACTORY_DIR="$WORKSPACE/factory"
WIKI_DIR="$WORKSPACE/wiki"
SOURCES_DIR="$WORKSPACE/sources"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ALL_PROFILES=(
  boss supervisor hr conductor
  growth eng brand
  room-engine video distro sermons creators dev churches
)

# ============================================================
# PRECHECKS
# ============================================================

echo "=== JESUSCORD FACTORY INSTALL ==="
echo

command -v hermes >/dev/null 2>&1 || { echo "ERROR: hermes not in PATH" >&2; exit 1; }
echo "[OK] hermes: $(hermes --version 2>/dev/null | head -1)"

: "${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN env var}"
: "${TELEGRAM_CHAT_ID:?Set TELEGRAM_CHAT_ID env var}"
: "${OPENROUTER_API_KEY:?Set OPENROUTER_API_KEY env var}"
echo "[OK] credentials present"

command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux required (sudo apt install tmux)" >&2; exit 1; }
command -v jq   >/dev/null 2>&1 || { echo "ERROR: jq required (sudo apt install jq)" >&2; exit 1; }
echo "[OK] tmux + jq present"

[[ -d "$(dirname "$WORKSPACE")" ]] || { echo "ERROR: $(dirname "$WORKSPACE") missing" >&2; exit 1; }

# ============================================================
# STEP 1 — Filesystem bus
# ============================================================

echo
echo "=== STEP 1: Filesystem bus ==="

mkdir -p "$WORKSPACE"
mkdir -p "$FACTORY_DIR"/{orders,approved_orders,assignments,inbox,outbox,status,drafts,approvals,decisions,escalations,locks}
mkdir -p "$FACTORY_DIR"/drafts/{emails,social,pitches,room_concepts,videos}
mkdir -p "$FACTORY_DIR"/approvals/{emails,social,pitches,paid_spend,room_concepts,videos}
for p in "${ALL_PROFILES[@]}"; do
  mkdir -p "$FACTORY_DIR/inbox/$p" "$FACTORY_DIR/outbox/$p"
done

mkdir -p "$WIKI_DIR"/{audience,voice,competitive,pastors,creators,churches,conferences,opportunities,campaigns,lessons,skills-library,branding,runbooks,feature_pipeline,memory-promotions}
mkdir -p "$SOURCES_DIR"/{pastors,corpus,platforms,transcripts,public,inbound}

touch "$FACTORY_DIR/activity.log" "$FACTORY_DIR/BLACKBOARD.md" "$FACTORY_DIR/PRIORITIZE.md"

cp "$THIS_DIR/06_protocol.md"          "$FACTORY_DIR/PROTOCOL.md"
cp "$THIS_DIR/HARD_RULES.md"           "$FACTORY_DIR/HARD_RULES.md"
cp "$THIS_DIR/STANDING_APPROVALS.md"   "$FACTORY_DIR/STANDING_APPROVALS.md"
chmod 444 "$FACTORY_DIR/HARD_RULES.md"

# QUIET_HOURS.md — founder customizes this
cat > "$FACTORY_DIR/QUIET_HOURS.md" <<'EOF'
quiet_hours_local:
  start: "23:00"
  end:   "07:00"
timezone: "Asia/Taipei"
batch_reminder_hours: 3
morning_digest_at: "07:30"
EOF

# Initial empty brand/strategy files (brand profile populates)
for f in BRAND_VOICE.md MESSAGE_FRAMEWORK.md CAMPAIGNS_ACTIVE.md POSITIONING.md CONTENT_PILLARS.md CALENDAR.md DIRECTIVES.md PERFORMANCE.md; do
  [[ -f "$FACTORY_DIR/$f" ]] || echo "# $f — pending generation by brand profile" > "$FACTORY_DIR/$f"
done

echo "[OK] bus at $FACTORY_DIR"
echo "[OK] wiki at $WIKI_DIR"

# ============================================================
# STEP 2 — Karpathy SCHEMA.md
# ============================================================

cat > "$WIKI_DIR/SCHEMA.md" <<'EOF'
# Karpathy Wiki Schema (Layer 3)

Layer 1 sources/: immutable. Append, never edit.
Layer 2 wiki/: curated synthesis. Mutable.
Layer 3 this file: rules. Only command line edits via decision.

Promotion: fact graduates from MEMORY.md → wiki when:
1. Referenced 3+ times across sessions, OR
2. Boss explicitly promotes via /promote, OR
3. Skill returns structured output with promote: true

Cross-refs: Obsidian-style [[wikilinks]]. Indexer regenerates wiki/INDEX.md on every wiki write.

Frontmatter (every wiki page):
---
title: ...
type: pastor | creator | church | conference | campaign | audience | competitor | voice | opportunity | lesson
created_by: <profile>
created_at: <ISO8601>
updated_at: <ISO8601>
sources: [<paths under sources/>]
confidence: low | medium | high
review_status: draft | reviewed | promoted
---

NOT in wiki:
- Drafts → factory/drafts/
- Status → factory/status/
- Orders → factory/orders/
- Performance → factory/PERFORMANCE.md
EOF

echo "[OK] SCHEMA.md written"

# ============================================================
# STEP 3 — Profile creation (14 profiles)
# ============================================================

echo
echo "=== STEP 3: Profile creation ==="

MASTER_SOUL="$THIS_DIR/02_SOUL_MASTER.md"
[[ -f "$MASTER_SOUL" ]] || { echo "ERROR: 02_SOUL_MASTER.md missing" >&2; exit 1; }

ensure_profile() {
  local name="$1"
  local home_dir="$HOME/.hermes-$name"

  if hermes profile list 2>/dev/null | grep -q "^\s*$name\s"; then
    echo "[SKIP] profile '$name' exists"
  else
    HERMES_HOME="$home_dir" hermes setup --non-interactive 2>/dev/null || \
      hermes profile create "$name" --no-alias 2>/dev/null || \
      mkdir -p "$home_dir"
    echo "[OK] profile '$name' at $home_dir"
  fi

  mkdir -p "$home_dir/skills" "$home_dir/cron"

  cp "$MASTER_SOUL" "$home_dir/SOUL.md"

  cat > "$home_dir/AGENTS.md" <<EOF
# AGENTS.md for $name

Read order at every session start:
1. ~/.hermes-$name/SOUL.md
2. $FACTORY_DIR/PROTOCOL.md
3. $FACTORY_DIR/HARD_RULES.md
4. $FACTORY_DIR/STANDING_APPROVALS.md
5. ~/.hermes-$name/TEAM_SOUL.md
6. $FACTORY_DIR/DIRECTIVES.md
7. $FACTORY_DIR/BRAND_VOICE.md
8. $WIKI_DIR/SCHEMA.md

Then PRIORITIZE.md, QUIET_HOURS.md, HALT_$name.flag (sleep if present).
Process inbox at $FACTORY_DIR/inbox/$name/.
Heartbeat to $FACTORY_DIR/status/$name.json every cycle.

Profile: $name
Workspace: $WORKSPACE
Wiki: $WIKI_DIR
Bus: $FACTORY_DIR
EOF

  if [[ ! -f "$home_dir/config.yaml" ]]; then
    cat > "$home_dir/config.yaml" <<EOF
profile_name: $name
agent:
  max_turns: 250
display:
  streaming: true
EOF
  fi

  cat > "$FACTORY_DIR/status/$name.json" <<EOF
{
  "profile": "$name",
  "host": "$(hostname)",
  "deployed_at": "$(date -Iseconds)",
  "version": "factory-v2.0",
  "halted": false,
  "current_task": null
}
EOF
}

for p in "${ALL_PROFILES[@]}"; do
  ensure_profile "$p"
done

# ============================================================
# STEP 4 — Inject team-specific souls
# ============================================================

echo
echo "=== STEP 4: TEAM_SOUL.md injection ==="

inject_soul_section() {
  local source_file="$1"
  local section_marker="$2"
  local profile_name="$3"
  local marker_prefix="$4"

  awk -v marker="$section_marker" -v prefix="$marker_prefix" '
    BEGIN { found=0; printing=0 }
    $0 ~ ("^" prefix) { if (printing) exit; if ($0 ~ marker) { printing=1; next } }
    printing { print }
  ' "$source_file" > "$HOME/.hermes-$profile_name/TEAM_SOUL.md"
  echo "[OK] $profile_name TEAM_SOUL.md injected"
}

# Top tier (boss, supervisor, hr, conductor) from 03_top_tier_souls.md
inject_soul_section "$THIS_DIR/03_top_tier_souls.md" "boss"        boss        "## ROLE: "
inject_soul_section "$THIS_DIR/03_top_tier_souls.md" "supervisor"  supervisor  "## ROLE: "
inject_soul_section "$THIS_DIR/03_top_tier_souls.md" "hr"          hr          "## ROLE: "
inject_soul_section "$THIS_DIR/03_top_tier_souls.md" "conductor"   conductor   "## ROLE: "

# Specialists (growth, eng, brand) from 04_specialist_souls.md
inject_soul_section "$THIS_DIR/04_specialist_souls.md" "growth"  growth  "## ROLE: "
inject_soul_section "$THIS_DIR/04_specialist_souls.md" "eng"     eng     "## ROLE: "
inject_soul_section "$THIS_DIR/04_specialist_souls.md" "brand"   brand   "## ROLE: "

# Teams from 05_team_souls.md
inject_soul_section "$THIS_DIR/05_team_souls.md" "room-engine"  room-engine  "## TEAM: "
inject_soul_section "$THIS_DIR/05_team_souls.md" "video"        video        "## TEAM: "
inject_soul_section "$THIS_DIR/05_team_souls.md" "distro"       distro       "## TEAM: "
inject_soul_section "$THIS_DIR/05_team_souls.md" "sermons"      sermons      "## TEAM: "
inject_soul_section "$THIS_DIR/05_team_souls.md" "creators"     creators     "## TEAM: "
inject_soul_section "$THIS_DIR/05_team_souls.md" "dev"          dev          "## TEAM: "
inject_soul_section "$THIS_DIR/05_team_souls.md" "churches"     churches     "## TEAM: "

# ============================================================
# STEP 5 — Auth
# ============================================================

echo
echo "=== STEP 5: Auth ==="

for p in "${ALL_PROFILES[@]}"; do
  HERMES_HOME="$HOME/.hermes-$p" hermes auth add openrouter --api-key "$OPENROUTER_API_KEY" 2>/dev/null || true
  [[ -n "${OPENAI_API_KEY:-}" ]] && \
    HERMES_HOME="$HOME/.hermes-$p" hermes auth add openai --api-key "$OPENAI_API_KEY" 2>/dev/null || true
  [[ -n "${ANTHROPIC_API_KEY:-}" ]] && \
    HERMES_HOME="$HOME/.hermes-$p" hermes auth add anthropic --api-key "$ANTHROPIC_API_KEY" 2>/dev/null || true
done
echo "[OK] auth registered"

# ============================================================
# STEP 6 — HUMAN_SECRET (for supervisor signature)
# ============================================================

SECRET_PATH="$HOME/.hermes-supervisor/.factory_human_secret"
if [[ ! -f "$SECRET_PATH" ]]; then
  openssl rand -hex 32 > "$SECRET_PATH"
  chmod 600 "$SECRET_PATH"
  echo "[OK] HUMAN_SECRET generated at $SECRET_PATH"
else
  echo "[SKIP] HUMAN_SECRET exists"
fi

# Distribute secret to all profiles (so they can verify supervisor signatures)
for p in "${ALL_PROFILES[@]}"; do
  cp "$SECRET_PATH" "$HOME/.hermes-$p/.factory_human_secret"
  chmod 600 "$HOME/.hermes-$p/.factory_human_secret"
done

# ============================================================
# STEP 7 — Telegram gateway (supervisor owns)
# ============================================================

echo
echo "=== STEP 7: Telegram gateway ==="

SUPERVISOR_HOME="$HOME/.hermes-supervisor"
mkdir -p "$SUPERVISOR_HOME"
cat >> "$SUPERVISOR_HOME/config.yaml" <<EOF

gateway:
  telegram:
    enabled: true
    bot_token: \${TELEGRAM_BOT_TOKEN}
    default_chat_id: $TELEGRAM_CHAT_ID
    webhook_secret: $(openssl rand -hex 16)
EOF

cat > "$SUPERVISOR_HOME/.env" <<EOF
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID
EOF
chmod 600 "$SUPERVISOR_HOME/.env"

if ! tmux has-session -t hermes-gateway 2>/dev/null; then
  tmux new-session -d -s hermes-gateway "HERMES_HOME=$SUPERVISOR_HOME hermes gateway run"
  echo "[OK] gateway in tmux 'hermes-gateway'"
else
  echo "[SKIP] gateway tmux exists"
fi

# ============================================================
# STEP 8 — MCP servers
# ============================================================

echo
echo "=== STEP 8: MCP servers ==="

for p in "${ALL_PROFILES[@]}"; do
  HERMES_HOME="$HOME/.hermes-$p" hermes mcp add filesystem-wiki \
    --command "npx" --args "-y" "@modelcontextprotocol/server-filesystem" "$WIKI_DIR" 2>/dev/null || true
  HERMES_HOME="$HOME/.hermes-$p" hermes mcp add filesystem-bus \
    --command "npx" --args "-y" "@modelcontextprotocol/server-filesystem" "$FACTORY_DIR" 2>/dev/null || true
done
echo "[OK] MCP filesystem servers added"

# ============================================================
# STEP 9 — Obsidian vault
# ============================================================

echo
echo "=== STEP 9: Obsidian ==="

mkdir -p "$(dirname "$OBSIDIAN_VAULT")"
if [[ ! -L "$OBSIDIAN_VAULT" ]]; then
  if [[ -d "$OBSIDIAN_VAULT" ]]; then
    mv "$OBSIDIAN_VAULT" "$OBSIDIAN_VAULT.bak.$(date +%s)"
  fi
  ln -s "$WIKI_DIR" "$OBSIDIAN_VAULT"
fi

mkdir -p "$WIKI_DIR/.obsidian"
cat > "$WIKI_DIR/.obsidian/app.json" <<'EOF'
{"alwaysUpdateLinks": true, "newLinkFormat": "shortest", "useMarkdownLinks": false, "showInlineTitle": true, "showFrontmatter": true}
EOF
cat > "$WIKI_DIR/.obsidian/community-plugins.json" <<'EOF'
["dataview", "templater-obsidian"]
EOF

echo "[OK] Obsidian vault: $OBSIDIAN_VAULT"

# ============================================================
# STEP 10 — Cron registration
# ============================================================

echo
echo "=== STEP 10: Cron registration ==="

if [[ -f "$THIS_DIR/08_install_cron.sh" ]]; then
  bash "$THIS_DIR/08_install_cron.sh"
else
  echo "[INFO] 08_install_cron.sh not found — extract from 08_cron.md and run separately"
fi

# ============================================================
# STEP 11 — Boot tmux sessions
# ============================================================

echo
echo "=== STEP 11: Boot ==="

BOOT_PROMPT="Read your AGENTS.md, SOUL.md, TEAM_SOUL.md in full. Then $FACTORY_DIR/PROTOCOL.md, $FACTORY_DIR/HARD_RULES.md, $FACTORY_DIR/STANDING_APPROVALS.md, $FACTORY_DIR/QUIET_HOURS.md, $FACTORY_DIR/DIRECTIVES.md, $FACTORY_DIR/BRAND_VOICE.md. Enter your operating loop per TEAM_SOUL.md. Write your first heartbeat. Write your first cycle output now. No preamble. Execute."

boot_profile() {
  local name="$1"
  local session="hermes-$name"
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "[SKIP] $session running"
    return
  fi
  tmux new-session -d -s "$session" -c "$WORKSPACE" \
    "HERMES_HOME=$HOME/.hermes-$name hermes chat --yolo"
  sleep 2
  tmux send-keys -t "$session" "$BOOT_PROMPT" Enter
  echo "[OK] $session booted (--yolo)"
}

for p in "${ALL_PROFILES[@]}"; do
  boot_profile "$p"
done

# ============================================================
# DONE
# ============================================================

echo
echo "============================================================"
echo "JESUSCORD FACTORY v2.0 DEPLOY COMPLETE"
echo "============================================================"
echo
echo "  Profiles:        14 / 14 (boss, supervisor, hr, conductor,"
echo "                   growth, eng, brand,"
echo "                   room-engine, video, distro, sermons,"
echo "                   creators, dev, churches)"
echo "  Workspace:       $WORKSPACE"
echo "  Wiki:            $WIKI_DIR"
echo "  Obsidian vault:  $OBSIDIAN_VAULT"
echo "  Telegram bot:    $TELEGRAM_CHAT_ID (via supervisor profile)"
echo "  Mode:            --yolo bridge (until megaprompts 09+10 applied)"
echo
echo "  Tmux sessions (15 = 14 profiles + 1 gateway):"
tmux ls 2>/dev/null | sed 's/^/    /'
echo
echo "  Halt all profiles: touch $FACTORY_DIR/EMERGENCY_HALT.flag"
echo "  Resume:            rm $FACTORY_DIR/EMERGENCY_HALT.flag"
echo "  Watch activity:    tail -f $FACTORY_DIR/activity.log"
echo
echo "  First Telegram digest fires at next top-of-hour."
echo "  Open Obsidian, point at vault — wiki populates in real time."
echo "============================================================"
