#!/usr/bin/env bash
# yolo_bridge.sh — switch all 14 profiles to/from --yolo mode

set -euo pipefail

WORKSPACE="${WORKSPACE:-/mnt/c/Users/$(whoami)/Desktop/JESUSCORD}"
FACTORY_DIR="$WORKSPACE/factory"

ALL_PROFILES=(boss supervisor hr conductor growth eng brand room-engine video distro sermons creators dev churches)

MODE="${1:-status}"

boot_prompt() {
  cat <<EOF
Read AGENTS.md, SOUL.md, TEAM_SOUL.md. Then $FACTORY_DIR/PROTOCOL.md, HARD_RULES.md, STANDING_APPROVALS.md, QUIET_HOURS.md, DIRECTIVES.md, BRAND_VOICE.md, MESSAGE_FRAMEWORK.md, CAMPAIGNS_ACTIVE.md. Enter operating loop. Heartbeat. Resume cycle. No preamble.
EOF
}

case "$MODE" in
  on)
    echo "=== YOLO BRIDGE ON ==="
    echo "Booting 14 profiles in --yolo. Hermes UI prompts off."
    echo "Factory gates (HARD_RULES §3, STANDING_APPROVALS, supervisor sig) still apply."
    echo
    for p in "${ALL_PROFILES[@]}"; do
      tmux kill-session -t "hermes-$p" 2>/dev/null || true
      tmux new-session -d -s "hermes-$p" -c "$WORKSPACE" \
        "HERMES_HOME=$HOME/.hermes-$p hermes chat --yolo"
      sleep 2
      tmux send-keys -t "hermes-$p" "$(boot_prompt)" Enter
      echo "[OK] $p (--yolo)"
    done
    echo
    echo "After megaprompt 09 applied to your hermes fork:"
    echo "  bash yolo_bridge.sh off"
    ;;

  off)
    echo "=== YOLO BRIDGE OFF ==="
    echo "Booting WITHOUT --yolo. Setting agent.approval_policy.mode=factory."
    echo
    for p in "${ALL_PROFILES[@]}"; do
      HERMES_HOME="$HOME/.hermes-$p" hermes config set agent.approval_policy.mode factory 2>/dev/null \
        && echo "[OK] $p: approval_policy.mode = factory" \
        || echo "[INFO] $p: approval_policy not available (megaprompt 09 not applied?)"
      HERMES_HOME="$HOME/.hermes-$p" hermes config set agent.ai_time_mode true 2>/dev/null || true

      tmux kill-session -t "hermes-$p" 2>/dev/null || true
      tmux new-session -d -s "hermes-$p" -c "$WORKSPACE" \
        "HERMES_HOME=$HOME/.hermes-$p hermes chat"
      sleep 2
      tmux send-keys -t "hermes-$p" "$(boot_prompt)" Enter
      echo "[OK] $p (no --yolo)"
    done
    ;;

  status)
    echo "=== PROFILE STATUS ==="
    for p in "${ALL_PROFILES[@]}"; do
      if tmux has-session -t "hermes-$p" 2>/dev/null; then
        if tmux capture-pane -t "hermes-$p" -p 2>/dev/null | grep -q -- "--yolo"; then
          mode="--yolo"
        else
          mode="normal"
        fi
        echo "  $p: alive ($mode)"
      else
        echo "  $p: NOT RUNNING"
      fi
    done
    echo
    echo "Heartbeats:"
    if [[ -d "$FACTORY_DIR/status" ]]; then
      for f in "$FACTORY_DIR/status"/*.json; do
        [[ -f "$f" ]] && {
          name=$(basename "$f" .json)
          last=$(jq -r '.last_cycle_at // "never"' "$f" 2>/dev/null || echo "?")
          echo "  $name: last cycle $last"
        }
      done
    fi
    ;;

  *)
    echo "Usage: $0 {on|off|status}"
    exit 1
    ;;
esac
