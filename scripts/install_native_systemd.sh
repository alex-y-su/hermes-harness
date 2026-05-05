#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${HERMES_SERVICE_USER:-$(id -un)}"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
HERMES_HOME="${HERMES_HOME:-/opt/hermes-home}"
HERMES_INSTALL_DIR="${HERMES_INSTALL_DIR:-$HERMES_HOME/hermes-agent}"
FACTORY_DIR="${FACTORY_DIR:-/factory}"
HARNESS_SQLITE_PATH="${HARNESS_SQLITE_PATH:-$FACTORY_DIR/harness.sqlite3}"
HARNESS_VENV="${HARNESS_VENV:-$ROOT_DIR/.venv}"
CODEX_HOME="${CODEX_HOME:-$SERVICE_HOME/.codex}"
HERMES_BIN="${HERMES_BIN:-$SERVICE_HOME/.local/bin/hermes}"
HERMES_A2A_PUBLIC_URL="${HERMES_A2A_PUBLIC_URL:-http://127.0.0.1:8080/}"
HERMES_A2A_BASE_PORT="${HERMES_A2A_BASE_PORT:-8080}"
HERMES_A2A_BIND_HOST="${HERMES_A2A_BIND_HOST:-0.0.0.0}"
HERMES_A2A_PUBLIC_HOST="${HERMES_A2A_PUBLIC_HOST:-127.0.0.1}"
HARNESS_A2A_BRIDGE_PORT="${HARNESS_A2A_BRIDGE_PORT:-8787}"
HARNESS_VIEWER_HOST="${HARNESS_VIEWER_HOST:-0.0.0.0}"
HARNESS_VIEWER_PORT="${HARNESS_VIEWER_PORT:-8090}"
HARNESS_ORCHESTRATOR_POLL_SECONDS="${HARNESS_ORCHESTRATOR_POLL_SECONDS:-30}"
HARNESS_ORCHESTRATOR_STALE_MINUTES="${HARNESS_ORCHESTRATOR_STALE_MINUTES:-15}"
HARNESS_ORCHESTRATOR_LEASE_TTL_SECONDS="${HARNESS_ORCHESTRATOR_LEASE_TTL_SECONDS:-60}"
HARNESS_BLOCKED_SANDBOX_TTL_MINUTES="${HARNESS_BLOCKED_SANDBOX_TTL_MINUTES:-240}"
HARNESS_ORPHAN_SANDBOX_TTL_MINUTES="${HARNESS_ORPHAN_SANDBOX_TTL_MINUTES:-60}"
HARNESS_ENV_PATH="${HARNESS_ENV_PATH:-$ROOT_DIR/.bridge.env}"
HARNESS_VIEWER_ENV_FILE="${HARNESS_VIEWER_ENV_FILE:-$ROOT_DIR/.viewer.env}"
SYSTEMD_ENV_DIR="${HERMES_NATIVE_SYSTEMD_ENV_DIR:-/etc/hermes-harness}"
SYSTEMD_ENV_FILE="$SYSTEMD_ENV_DIR/native.env"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v sudo >/dev/null 2>&1 || fail "sudo is required to install systemd units"
[ -d "$SERVICE_HOME" ] || fail "home directory for $SERVICE_USER not found"
[ -f "$CODEX_HOME/auth.json" ] || fail "Codex auth not found at $CODEX_HOME/auth.json"
[ -f "$HARNESS_ENV_PATH" ] || fail "bridge env file not found at $HARNESS_ENV_PATH"
[ -f "$HARNESS_VIEWER_ENV_FILE" ] || fail "viewer env file not found at $HARNESS_VIEWER_ENV_FILE"

sudo mkdir -p "$FACTORY_DIR" "$HERMES_HOME"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$FACTORY_DIR" "$HERMES_HOME"

python3 -m venv "$HARNESS_VENV"
"$HARNESS_VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$HARNESS_VENV/bin/python" -m pip install -e "$ROOT_DIR[e2b]"

if [ "${HERMES_NATIVE_SKIP_BOOTSTRAP:-0}" != "1" ]; then
  env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u OPENROUTER_API_KEY_AIWIZ_LANDING -u LLM_BASE_URL \
    ROOT_DIR="$ROOT_DIR" \
    HERMES_HOME="$HERMES_HOME" \
    HERMES_INSTALL_DIR="$HERMES_INSTALL_DIR" \
    FACTORY_DIR="$FACTORY_DIR" \
    HARNESS_FACTORY="$FACTORY_DIR" \
    CODEX_HOME="$CODEX_HOME" \
    HERMES_BOOTSTRAP_BACKUP_ROOT="${HERMES_BOOTSTRAP_BACKUP_ROOT:-/tmp}" \
    HERMES_BOOTSTRAP_FORCE_PIN="${HERMES_BOOTSTRAP_FORCE_PIN:-1}" \
    HERMES_A2A_BASE_PORT="$HERMES_A2A_BASE_PORT" \
    HERMES_A2A_BIND_HOST="$HERMES_A2A_BIND_HOST" \
    HERMES_A2A_PUBLIC_HOST="$HERMES_A2A_PUBLIC_HOST" \
    HERMES_A2A_PUBLIC_URL="$HERMES_A2A_PUBLIC_URL" \
    "$ROOT_DIR/scripts/bootstrap_hermes_agent.sh"
fi

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$HARNESS_SQLITE_PATH" < "$ROOT_DIR/schema/sqlite.sql"
fi
"$HARNESS_VENV/bin/python" - <<PY
from pathlib import Path
from harness.db import init_db
init_db(Path("$HARNESS_SQLITE_PATH"))
PY

sudo mkdir -p "$SYSTEMD_ENV_DIR"
sudo tee "$SYSTEMD_ENV_FILE" >/dev/null <<EOF
ROOT_DIR=$ROOT_DIR
HERMES_HOME=$HERMES_HOME
HERMES_INSTALL_DIR=$HERMES_INSTALL_DIR
FACTORY_DIR=$FACTORY_DIR
HARNESS_FACTORY=$FACTORY_DIR
HARNESS_FACTORY_DIR=$FACTORY_DIR
HARNESS_SQLITE_PATH=$HARNESS_SQLITE_PATH
HARNESS_ENV_PATH=$HARNESS_ENV_PATH
CODEX_HOME=$CODEX_HOME
HERMES_BIN=$HERMES_BIN
HERMES_A2A_BASE_PORT=$HERMES_A2A_BASE_PORT
HERMES_A2A_BIND_HOST=$HERMES_A2A_BIND_HOST
HERMES_A2A_PUBLIC_HOST=$HERMES_A2A_PUBLIC_HOST
HERMES_A2A_PUBLIC_URL=$HERMES_A2A_PUBLIC_URL
HERMES_A2A_FOREGROUND=1
HARNESS_A2A_BRIDGE_PORT=$HARNESS_A2A_BRIDGE_PORT
HARNESS_VIEWER_HOST=$HARNESS_VIEWER_HOST
HARNESS_VIEWER_PORT=$HARNESS_VIEWER_PORT
HARNESS_VIEWER_QUIET=1
HARNESS_ORCHESTRATOR_POLL_SECONDS=$HARNESS_ORCHESTRATOR_POLL_SECONDS
HARNESS_ORCHESTRATOR_STALE_MINUTES=$HARNESS_ORCHESTRATOR_STALE_MINUTES
HARNESS_ORCHESTRATOR_LEASE_TTL_SECONDS=$HARNESS_ORCHESTRATOR_LEASE_TTL_SECONDS
HARNESS_BLOCKED_SANDBOX_TTL_MINUTES=$HARNESS_BLOCKED_SANDBOX_TTL_MINUTES
HARNESS_ORPHAN_SANDBOX_TTL_MINUTES=$HARNESS_ORPHAN_SANDBOX_TTL_MINUTES
PYTHONPATH=$ROOT_DIR
PATH=$HARNESS_VENV/bin:$SERVICE_HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EOF

sudo tee /etc/systemd/system/hermes-boss-a2a.service >/dev/null <<EOF
[Unit]
Description=Hermes Harness boss A2A endpoint
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$SYSTEMD_ENV_FILE
UnsetEnvironment=OPENAI_API_KEY OPENROUTER_API_KEY OPENROUTER_API_KEY_AIWIZ_LANDING LLM_BASE_URL
ExecStart=$ROOT_DIR/scripts/start_hermes_a2a_team.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hermes-boss-gateway.service >/dev/null <<EOF
[Unit]
Description=Hermes Harness boss Hermes gateway and cron runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$SYSTEMD_ENV_FILE
UnsetEnvironment=OPENAI_API_KEY OPENROUTER_API_KEY OPENROUTER_API_KEY_AIWIZ_LANDING LLM_BASE_URL
ExecStart=$HERMES_BIN --profile boss gateway run --accept-hooks
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hermes-bridge.service >/dev/null <<EOF
[Unit]
Description=Hermes Harness A2A bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$SYSTEMD_ENV_FILE
UnsetEnvironment=OPENAI_API_KEY OPENROUTER_API_KEY OPENROUTER_API_KEY_AIWIZ_LANDING LLM_BASE_URL
ExecStart=$HARNESS_VENV/bin/python -m harness.bridge.cli --factory $FACTORY_DIR --db $HARNESS_SQLITE_PATH --env $HARNESS_ENV_PATH --port $HARNESS_A2A_BRIDGE_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hermes-viewer.service >/dev/null <<EOF
[Unit]
Description=Hermes Harness web viewer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$SYSTEMD_ENV_FILE
EnvironmentFile=$HARNESS_VIEWER_ENV_FILE
ExecStart=$HARNESS_VENV/bin/python -m harness.viewer.server --factory $FACTORY_DIR --db $HARNESS_SQLITE_PATH --host $HARNESS_VIEWER_HOST --port $HARNESS_VIEWER_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hermes-orchestrator.service >/dev/null <<EOF
[Unit]
Description=Hermes Harness assignment watchdog and orchestrator
After=network-online.target hermes-bridge.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$SYSTEMD_ENV_FILE
ExecStart=$HARNESS_VENV/bin/python -m harness.tools.orchestrator --factory $FACTORY_DIR --db $HARNESS_SQLITE_PATH --loop
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hermes-boss-a2a hermes-boss-gateway hermes-bridge hermes-viewer hermes-orchestrator

if [ "${HERMES_NATIVE_START_SERVICES:-1}" = "1" ]; then
  sudo systemctl restart hermes-boss-a2a hermes-boss-gateway hermes-bridge hermes-viewer hermes-orchestrator
fi

echo "Installed native Hermes Harness systemd services."
echo "A2A:    $HERMES_A2A_PUBLIC_URL"
echo "Viewer: http://$HARNESS_VIEWER_HOST:$HARNESS_VIEWER_PORT/"
echo "Bridge: http://127.0.0.1:$HARNESS_A2A_BRIDGE_PORT/"
echo "Orchestrator: hermes-orchestrator.service"
