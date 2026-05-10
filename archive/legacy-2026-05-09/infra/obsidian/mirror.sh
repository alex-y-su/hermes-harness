#!/usr/bin/env bash
set -euo pipefail

FACTORY_DIR="${FACTORY_DIR:?Set FACTORY_DIR}"
OBSIDIAN_VAULT="${OBSIDIAN_VAULT:?Set OBSIDIAN_VAULT}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

mkdir -p "$OBSIDIAN_VAULT/factory"

rsync -a --delete \
  --include='/orders/***' \
  --include='/approved_orders/***' \
  --include='/assignments/***' \
  --include='/inbox/***' \
  --include='/outbox/***' \
  --include='/drafts/***' \
  --include='/decisions/***' \
  --include='/escalations/***' \
  --include='/blackboard/***' \
  --include='/status/***' \
  --include='/teams/' \
  --include='/teams/*/' \
  --include='/teams/*/brief.md' \
  --include='/teams/*/TEAM_SOUL.md' \
  --include='/teams/*/status.json' \
  --include='/teams/*/journal.md' \
  --include='/teams/*/criteria.md' \
  --include='/teams/*/outbox/***' \
  --exclude-from="$ROOT_DIR/infra/obsidian/excludes.txt" \
  --exclude='*' \
  "$FACTORY_DIR/" "$OBSIDIAN_VAULT/factory/"
