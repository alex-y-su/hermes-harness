#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-$PWD}"
FACTORY_DIR="${FACTORY_DIR:-$WORKSPACE/factory}"
HARNESS_SQLITE_PATH="${HARNESS_SQLITE_PATH:-$FACTORY_DIR/harness.sqlite3}"
HARNESS_ENV_PATH="${HARNESS_ENV_PATH:-}"
BOSS_PUSH_URL="${BOSS_PUSH_URL:-}"
OBSIDIAN_VAULT="${OBSIDIAN_VAULT:-}"

PROFILES=(boss supervisor hr conductor critic a2a-bridge)

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_env() {
  local name="$1"
  [[ -n "${!name:-}" ]] || fail "$name is required"
}

echo "=== Hermes Harness install ==="

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v sqlite3 >/dev/null 2>&1 || fail "sqlite3 is required"
command -v hermes >/dev/null 2>&1 || fail "hermes is required"

require_env HARNESS_ENV_PATH
require_env BOSS_PUSH_URL
[[ "$BOSS_PUSH_URL" == https://* ]] || fail "BOSS_PUSH_URL must be a public https:// URL"
[[ -f "$HARNESS_ENV_PATH" ]] || fail "HARNESS_ENV_PATH must point to an external .env file"
[[ "$HARNESS_ENV_PATH" != "$FACTORY_DIR"* ]] || fail "HARNESS_ENV_PATH must live outside factory/"

grep -q '^HARNESS_BRIDGE_SECRET=' "$HARNESS_ENV_PATH" || fail "HARNESS_ENV_PATH must define HARNESS_BRIDGE_SECRET"
if [[ "${HARNESS_ENABLE_E2B:-1}" != "0" ]]; then
  grep -q '^E2B_API_KEY=' "$HARNESS_ENV_PATH" || fail "HARNESS_ENV_PATH must define E2B_API_KEY when E2B is enabled"
fi

mkdir -p "$FACTORY_DIR"/{orders,approved_orders,assignments,inbox,outbox,status,drafts,approvals,decisions,escalations,locks,teams}
mkdir -p "$(dirname "$HARNESS_SQLITE_PATH")"

cp "$ROOT_DIR/docs/team/06_protocol.md" "$FACTORY_DIR/PROTOCOL.md"
cp "$ROOT_DIR/docs/team/HARD_RULES.md" "$FACTORY_DIR/HARD_RULES.md"
cp "$ROOT_DIR/docs/team/STANDING_APPROVALS.md" "$FACTORY_DIR/STANDING_APPROVALS.md"
cp "$ROOT_DIR/bus_template/QUIET_HOURS.md" "$FACTORY_DIR/QUIET_HOURS.md"
cp "$ROOT_DIR/bus_template/BLACKBOARD.md" "$FACTORY_DIR/BLACKBOARD.md"
cp "$ROOT_DIR/bus_template/PRIORITIZE.md" "$FACTORY_DIR/PRIORITIZE.md"
chmod 444 "$FACTORY_DIR/HARD_RULES.md"

for profile in "${PROFILES[@]}"; do
  mkdir -p "$FACTORY_DIR/inbox/$profile" "$FACTORY_DIR/outbox/$profile"
  home_dir="$HOME/.hermes-$profile"
  mkdir -p "$home_dir"
  cat > "$home_dir/AGENTS.md" <<EOF
# AGENTS.md for $profile

Read these files at session start:
1. $home_dir/SOUL.md
2. $FACTORY_DIR/PROTOCOL.md
3. $FACTORY_DIR/HARD_RULES.md
4. $FACTORY_DIR/STANDING_APPROVALS.md
5. $home_dir/TEAM_SOUL.md
6. $FACTORY_DIR/PRIORITIZE.md
7. $FACTORY_DIR/QUIET_HOURS.md

Factory: $FACTORY_DIR
Profile: $profile
EOF
  cat > "$home_dir/config.yaml" <<EOF
profile_name: $profile
agent:
  max_turns: 500
goals:
  max_turns: 1000
compression:
  threshold: 0.70
approvals:
  mode: off
hooks_auto_accept: true
delegation:
  max_iterations: 200
EOF
  [[ -f "$home_dir/SOUL.md" ]] || printf '# %s\n\nGeneric Hermes Harness profile.\n' "$profile" > "$home_dir/SOUL.md"
  [[ -f "$home_dir/TEAM_SOUL.md" ]] || printf '# %s TEAM_SOUL\n\nYou are running on a long-horizon mission. No human is waiting for a polished summary at the end of each cycle. Continue until criteria are met or you are hard-blocked.\n' "$profile" > "$home_dir/TEAM_SOUL.md"
done

python3 -m pip install -e "$ROOT_DIR"
sqlite3 "$HARNESS_SQLITE_PATH" < "$ROOT_DIR/schema/sqlite.sql"

mkdir -p "$HOME/.hermes/harness"
rm -rf "$HOME/.hermes/harness/templates"
cp -R "$ROOT_DIR/templates" "$HOME/.hermes/harness/templates"

cat > "$FACTORY_DIR/status/a2a-bridge.env" <<EOF
HARNESS_FACTORY_DIR=$FACTORY_DIR
HARNESS_SQLITE_PATH=$HARNESS_SQLITE_PATH
HARNESS_ENV_PATH=$HARNESS_ENV_PATH
HARNESS_A2A_BRIDGE_PORT=${HARNESS_A2A_BRIDGE_PORT:-8787}
BOSS_PUSH_URL=$BOSS_PUSH_URL
EOF

if [[ -n "$OBSIDIAN_VAULT" ]]; then
  mkdir -p "$OBSIDIAN_VAULT"
  cp "$ROOT_DIR/infra/obsidian/excludes.txt" "$OBSIDIAN_VAULT/.hermes-harness-excludes"
fi

echo
echo "Installed Hermes Harness."
echo "Factory: $FACTORY_DIR"
echo "SQLite: $HARNESS_SQLITE_PATH"
echo "Bridge:"
echo "  HARNESS_FACTORY_DIR=$FACTORY_DIR HARNESS_SQLITE_PATH=$HARNESS_SQLITE_PATH HARNESS_ENV_PATH=$HARNESS_ENV_PATH harness-a2a-bridge"
