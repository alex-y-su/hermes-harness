#!/usr/bin/env bash
set -euo pipefail

FACTORY_DIR="${FACTORY_DIR:-/factory}"
CONFIG_ROOT="${FACTORY_CONFIG_ROOT:-/factory-config}"
HERMES_HOME="${HERMES_HOME:-/opt/hermes-home}"
PROFILE_LAYOUT="${PROFILE_LAYOUT:-hermes-profiles}"
SERVICE_NAMES=(hermes-boss-a2a hermes-boss-gateway)
PROFILES=(boss supervisor hr conductor critic a2a-bridge)
CUSTOM_SKILLS=(wiki-write wiki-index-regen promote-to-wiki contradiction-detector source-ingest root-config-versioning)

usage() {
  cat <<'EOF'
Usage:
  scripts/factory_config_versions.sh migrate [label]
  scripts/factory_config_versions.sh new [label]
  scripts/factory_config_versions.sh switch <version> [--restart]
  scripts/factory_config_versions.sh status

Environment:
  FACTORY_DIR=/factory
  FACTORY_CONFIG_ROOT=/factory-config
  HERMES_HOME=/opt/hermes-home

This versions only definitions/goals/policies/blueprints/skills.
Runtime state, DBs, logs, queues, assignments, auth, and secrets stay outside versions.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

slug() {
  printf '%s' "${1:-manual}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_.-]+/-/g; s/^-+//; s/-+$//' | cut -c1-48
}

timestamp() {
  date -u +"%Y%m%dT%H%M%SZ"
}

version_name() {
  local label
  label="$(slug "${1:-manual}")"
  printf '%s_%s\n' "$(timestamp)" "${label:-manual}"
}

profile_dir() {
  local profile="$1"
  if [ "$PROFILE_LAYOUT" = "legacy" ]; then
    printf '%s/.hermes-%s\n' "$HERMES_HOME" "$profile"
  else
    printf '%s/profiles/%s\n' "$HERMES_HOME" "$profile"
  fi
}

current_link() {
  printf '%s/current\n' "$CONFIG_ROOT"
}

current_config_link() {
  printf '%s/current_config\n' "$FACTORY_DIR"
}

atomic_link() {
  local target="$1" link="$2"
  ln -sfn "$target" "$link.next"
  if mv -Tf "$link.next" "$link" 2>/dev/null; then
    return 0
  fi
  rm -f "$link"
  mv -f "$link.next" "$link"
}

copy_file() {
  local src="$1" dst="$2"
  [ -f "$src" ] || return 0
  mkdir -p "$(dirname "$dst")"
  cp -aL "$src" "$dst"
}

copy_dir() {
  local src="$1" dst="$2"
  [ -d "$src" ] || return 0
  rm -rf "$dst"
  mkdir -p "$(dirname "$dst")"
  cp -aL "$src" "$dst"
}

write_root_config_skill() {
  local dst="$1/skills/root-config-versioning/SKILL.md"
  mkdir -p "$(dirname "$dst")"
  cat > "$dst" <<'EOF'
# root-config-versioning

Use this skill whenever a user asks to change root-team behavior, goals, policies, schedules, role definitions, skills, or remote-team blueprints.

The active config is `/factory/current_config`, which points to a versioned folder under `/factory-config/versions/`.

Rules:
1. Do not edit old versions.
2. Before changing config, create a new version:
   `FACTORY_DIR=/factory FACTORY_CONFIG_ROOT=/factory-config HERMES_HOME=/opt/hermes-home /opt/hermes-harness/scripts/factory_config_versions.sh new <short-label>`
3. Edit only symlinked config paths under `/factory` or `/opt/hermes-home/profiles/*/{AGENTS.md,SOUL.md,TEAM_SOUL.md}`.
4. Show the user the changed paths and explain the rollback target.
5. To rollback, switch the symlink only after explicit user request:
   `/opt/hermes-harness/scripts/factory_config_versions.sh switch <version> --restart`

Versioned:
- goals, policies, protocol, object definitions
- root profile AGENTS/SOUL/TEAM_SOUL
- remote team blueprints
- root-team skills
- memory schema/templates

Never version or edit through this skill:
- auth.json, .env, bearer tokens, webhook secrets, .factory_human_secret
- SQLite DBs, status, logs, sessions, queues, assignments, team runtime folders, outbox artifacts
EOF
}

create_version_from_live() {
  local version="$1"
  local dir="$CONFIG_ROOT/versions/$version"
  [ ! -e "$dir" ] || die "version already exists: $version"
  mkdir -p "$dir"

  copy_file "$FACTORY_DIR/PRIORITIZE.md" "$dir/goals/PRIORITIZE.md"
  copy_file "$FACTORY_DIR/DIRECTIVES.md" "$dir/goals/DIRECTIVES.md"
  [ -f "$dir/goals/GOALS.md" ] || printf '# GOALS.md\n\n' > "$dir/goals/GOALS.md"
  [ -f "$dir/goals/AUTOPILOT.md" ] || printf '# AUTOPILOT.md\n\nmode: paused\n' > "$dir/goals/AUTOPILOT.md"

  copy_file "$FACTORY_DIR/STANDING_APPROVALS.md" "$dir/policies/STANDING_APPROVALS.md"
  copy_file "$FACTORY_DIR/QUIET_HOURS.md" "$dir/policies/QUIET_HOURS.md"
  copy_file "$FACTORY_DIR/HARD_RULES.md" "$dir/policies/HARD_RULES.md"
  copy_file "$FACTORY_DIR/PROTOCOL.md" "$dir/protocol/PROTOCOL.md"

  copy_file "$FACTORY_DIR/BRAND_VOICE.md" "$dir/objects/BRAND_VOICE.md"
  copy_file "$FACTORY_DIR/MESSAGE_FRAMEWORK.md" "$dir/objects/MESSAGE_FRAMEWORK.md"
  copy_file "$FACTORY_DIR/CAMPAIGNS_ACTIVE.md" "$dir/objects/CAMPAIGNS_ACTIVE.md"
  copy_file "$FACTORY_DIR/POSITIONING.md" "$dir/objects/POSITIONING.md"
  copy_file "$FACTORY_DIR/CONTENT_PILLARS.md" "$dir/objects/CONTENT_PILLARS.md"
  copy_file "$FACTORY_DIR/CALENDAR.md" "$dir/objects/CALENDAR.md"

  copy_dir "$FACTORY_DIR/team_blueprints" "$dir/team_blueprints"
  copy_dir "$FACTORY_DIR/skills" "$dir/skills"
  copy_file "$FACTORY_DIR/wiki/SCHEMA.md" "$dir/memory_schema/SCHEMA.md"
  copy_dir "$FACTORY_DIR/wiki/.templates" "$dir/memory_schema/templates"
  copy_dir "$FACTORY_DIR/wiki/.obsidian" "$dir/memory_schema/obsidian"

  for profile in "${PROFILES[@]}"; do
    local pdir
    pdir="$(profile_dir "$profile")"
    copy_file "$pdir/AGENTS.md" "$dir/profiles/$profile/AGENTS.md"
    copy_file "$pdir/SOUL.md" "$dir/profiles/$profile/SOUL.md"
    copy_file "$pdir/TEAM_SOUL.md" "$dir/profiles/$profile/TEAM_SOUL.md"
  done

  write_root_config_skill "$dir"
  cat > "$dir/VERSION.yaml" <<EOF
version: "$version"
created_at: "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
layout: root-team-config-v1
source: live-migration
runtime_state: excluded
secrets: excluded
EOF
  printf '%s\n' "$dir"
}

create_version_from_current() {
  local version="$1"
  local current
  current="$(readlink -f "$(current_link)")"
  [ -n "$current" ] && [ -d "$current" ] || die "current config is not initialized"
  local dir="$CONFIG_ROOT/versions/$version"
  [ ! -e "$dir" ] || die "version already exists: $version"
  mkdir -p "$(dirname "$dir")"
  cp -a "$current" "$dir"
  cat > "$dir/VERSION.yaml" <<EOF
version: "$version"
created_at: "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
layout: root-team-config-v1
source: "$current"
runtime_state: excluded
secrets: excluded
EOF
  write_root_config_skill "$dir"
  printf '%s\n' "$dir"
}

backup_path() {
  local path="$1" backup_root="$2"
  [ -e "$path" ] || [ -L "$path" ] || return 0
  mkdir -p "$backup_root/$(dirname "${path#/}")"
  mv "$path" "$backup_root/${path#/}"
}

link_path() {
  local target="$1" link="$2" backup_root="$3"
  if [ -L "$link" ]; then
    rm "$link"
  elif [ -e "$link" ]; then
    backup_path "$link" "$backup_root"
  fi
  mkdir -p "$(dirname "$link")"
  ln -s "$target" "$link"
}

link_live_paths() {
  local version="$1"
  local backup_root="$CONFIG_ROOT/migration-backups/$version"
  mkdir -p "$backup_root"
  atomic_link "$CONFIG_ROOT/versions/$version" "$(current_link)"
  atomic_link "$(current_link)" "$(current_config_link)"

  link_path "current_config/goals/PRIORITIZE.md" "$FACTORY_DIR/PRIORITIZE.md" "$backup_root"
  link_path "current_config/goals/DIRECTIVES.md" "$FACTORY_DIR/DIRECTIVES.md" "$backup_root"
  link_path "current_config/goals/GOALS.md" "$FACTORY_DIR/GOALS.md" "$backup_root"
  link_path "current_config/goals/AUTOPILOT.md" "$FACTORY_DIR/AUTOPILOT.md" "$backup_root"
  link_path "current_config/policies/STANDING_APPROVALS.md" "$FACTORY_DIR/STANDING_APPROVALS.md" "$backup_root"
  link_path "current_config/policies/QUIET_HOURS.md" "$FACTORY_DIR/QUIET_HOURS.md" "$backup_root"
  link_path "current_config/policies/HARD_RULES.md" "$FACTORY_DIR/HARD_RULES.md" "$backup_root"
  link_path "current_config/protocol/PROTOCOL.md" "$FACTORY_DIR/PROTOCOL.md" "$backup_root"

  link_path "current_config/objects/BRAND_VOICE.md" "$FACTORY_DIR/BRAND_VOICE.md" "$backup_root"
  link_path "current_config/objects/MESSAGE_FRAMEWORK.md" "$FACTORY_DIR/MESSAGE_FRAMEWORK.md" "$backup_root"
  link_path "current_config/objects/CAMPAIGNS_ACTIVE.md" "$FACTORY_DIR/CAMPAIGNS_ACTIVE.md" "$backup_root"
  link_path "current_config/objects/POSITIONING.md" "$FACTORY_DIR/POSITIONING.md" "$backup_root"
  link_path "current_config/objects/CONTENT_PILLARS.md" "$FACTORY_DIR/CONTENT_PILLARS.md" "$backup_root"
  link_path "current_config/objects/CALENDAR.md" "$FACTORY_DIR/CALENDAR.md" "$backup_root"

  link_path "current_config/team_blueprints" "$FACTORY_DIR/team_blueprints" "$backup_root"
  link_path "current_config/skills" "$FACTORY_DIR/skills" "$backup_root"
  link_path "../current_config/memory_schema/SCHEMA.md" "$FACTORY_DIR/wiki/SCHEMA.md" "$backup_root"
  link_path "../current_config/memory_schema/templates" "$FACTORY_DIR/wiki/.templates" "$backup_root"
  link_path "../current_config/memory_schema/obsidian" "$FACTORY_DIR/wiki/.obsidian" "$backup_root"

  for profile in "${PROFILES[@]}"; do
    local pdir
    pdir="$(profile_dir "$profile")"
    link_path "$FACTORY_DIR/current_config/profiles/$profile/AGENTS.md" "$pdir/AGENTS.md" "$backup_root"
    link_path "$FACTORY_DIR/current_config/profiles/$profile/SOUL.md" "$pdir/SOUL.md" "$backup_root"
    link_path "$FACTORY_DIR/current_config/profiles/$profile/TEAM_SOUL.md" "$pdir/TEAM_SOUL.md" "$backup_root"
    mkdir -p "$pdir/skills"
    for skill in "${CUSTOM_SKILLS[@]}"; do
      [ -d "$FACTORY_DIR/current_config/skills/$skill" ] || continue
      link_path "$FACTORY_DIR/current_config/skills/$skill" "$pdir/skills/$skill" "$backup_root"
    done
  done
  echo "$backup_root" > "$CONFIG_ROOT/last_migration_backup.txt"
}

restart_services() {
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl restart "${SERVICE_NAMES[@]}"
  fi
}

cmd_migrate() {
  local version
  version="$(version_name "${1:-initial}")"
  mkdir -p "$CONFIG_ROOT/versions" "$CONFIG_ROOT/migration-backups"
  create_version_from_live "$version" >/dev/null
  link_live_paths "$version"
  echo "migrated config to $CONFIG_ROOT/versions/$version"
  echo "active config: $(readlink -f "$(current_config_link)")"
}

cmd_new() {
  local version
  version="$(version_name "${1:-chat-change}")"
  mkdir -p "$CONFIG_ROOT/versions"
  create_version_from_current "$version" >/dev/null
  atomic_link "$CONFIG_ROOT/versions/$version" "$(current_link)"
  echo "created and activated $version"
  echo "edit through $FACTORY_DIR symlinks; previous version remains unchanged"
}

cmd_switch() {
  local version="${1:-}"
  [ -n "$version" ] || die "switch requires a version"
  local restart="${2:-}"
  local target="$CONFIG_ROOT/versions/$version"
  [ -d "$target" ] || die "version not found: $version"
  atomic_link "$target" "$(current_link)"
  echo "active config: $version"
  if [ "$restart" = "--restart" ]; then
    restart_services
    echo "restarted ${SERVICE_NAMES[*]}"
  fi
}

cmd_status() {
  echo "factory: $FACTORY_DIR"
  echo "config_root: $CONFIG_ROOT"
  echo "current: $(readlink -f "$(current_link)" 2>/dev/null || true)"
  echo
  echo "versions:"
  if [ -d "$CONFIG_ROOT/versions" ]; then
    for version_dir in "$CONFIG_ROOT"/versions/*; do
      [ -d "$version_dir" ] || continue
      basename "$version_dir"
    done | sort -r
  fi
}

main() {
  local command="${1:-}"
  shift || true
  case "$command" in
    migrate) cmd_migrate "${1:-initial}" ;;
    new) cmd_new "${1:-chat-change}" ;;
    switch) cmd_switch "${1:-}" "${2:-}" ;;
    status) cmd_status ;;
    -h|--help|help|"") usage ;;
    *) die "unknown command: $command" ;;
  esac
}

main "$@"
