#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="${HERMES_BIN:-$HOME/.local/bin/hermes}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_A2A_LOG_DIR="${HERMES_A2A_LOG_DIR:-$HERMES_HOME/a2a-logs}"
HERMES_A2A_PID_DIR="${HERMES_A2A_PID_DIR:-$HERMES_HOME/a2a-pids}"
HERMES_A2A_MANIFEST="${HERMES_A2A_MANIFEST:-$HERMES_HOME/a2a-team.json}"
INTERNAL_PROFILES=(supervisor hr conductor critic a2a-bridge)

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[ -x "$HERMES_BIN" ] || fail "Hermes executable not found at $HERMES_BIN"
mkdir -p "$HERMES_A2A_LOG_DIR" "$HERMES_A2A_PID_DIR"

for profile in "${INTERNAL_PROFILES[@]}"; do
  pid_file="$HERMES_A2A_PID_DIR/$profile.pid"
  if [ -f "$pid_file" ]; then
    old_pid="$(cat "$pid_file")"
    if kill "$old_pid" 2>/dev/null; then
      echo "stopped stale internal A2A endpoint $profile pid=$old_pid"
    fi
    rm -f "$pid_file"
  fi
done

profile_info="$(python3 - "$HERMES_A2A_MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).expanduser().read_text(encoding="utf-8"))
entry = data.get("public_agent") or next(item for item in data["profiles"] if item.get("public", item.get("profile") == "boss"))
print("\t".join([
    entry["profile"],
    entry.get("name") or entry["profile"],
    str(entry["url"]).rsplit(":", 1)[1],
    entry["auth_token"],
]))
PY
)"
profile="$(printf '%s' "$profile_info" | cut -f1)"
agent_name="$(printf '%s' "$profile_info" | cut -f2)"
port="$(printf '%s' "$profile_info" | cut -f3)"
token="$(printf '%s' "$profile_info" | cut -f4-)"

if [ -f "$HERMES_A2A_PID_DIR/$profile.pid" ]; then
  old_pid="$(cat "$HERMES_A2A_PID_DIR/$profile.pid")"
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "$profile user-facing A2A endpoint already running pid=$old_pid"
    echo "A2A public endpoint: http://${HERMES_A2A_PUBLIC_HOST:-127.0.0.1}:$port/"
    exit 0
  fi
fi

log="$HERMES_A2A_LOG_DIR/$profile.log"
public_url="${HERMES_A2A_PUBLIC_URL:-http://${HERMES_A2A_PUBLIC_HOST:-127.0.0.1}:$port/}"
if [ "${HERMES_A2A_FOREGROUND:-0}" = "1" ]; then
  unset OPENAI_API_KEY OPENROUTER_API_KEY OPENROUTER_API_KEY_AIWIZ_LANDING LLM_BASE_URL
  export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
  echo "starting user-facing $profile A2A endpoint in foreground"
  echo "A2A public endpoint: http://${HERMES_A2A_PUBLIC_HOST:-127.0.0.1}:$port/"
  exec python3 -m harness.tools.hermes_a2a_server \
    --profile "$profile" \
    --host "${HERMES_A2A_BIND_HOST:-127.0.0.1}" \
    --port "$port" \
    --token "$token" \
    --hermes-bin "$HERMES_BIN" \
    --agent-name "$agent_name" \
    --public-url "$public_url" \
    --description "User-facing Hermes Harness boss profile. Internal boss-team roles communicate through the local factory bus."
fi

pid="$(python3 - "$ROOT_DIR" "$profile" "$agent_name" "${HERMES_A2A_BIND_HOST:-127.0.0.1}" "$port" "$token" "$HERMES_BIN" "$log" "$public_url" <<'PY'
import os
import subprocess
import sys

root_dir, profile, agent_name, host, port, token, hermes_bin, log, public_url = sys.argv[1:]
env = dict(os.environ)
for key in list(env):
    if key.startswith("OPENAI_") or key.startswith("OPENROUTER_") or key == "LLM_BASE_URL":
        env.pop(key, None)
env["PYTHONPATH"] = root_dir + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
args = [
    sys.executable,
    "-m",
    "harness.tools.hermes_a2a_server",
    "--profile",
    profile,
    "--host",
    host,
    "--port",
    port,
    "--token",
    token,
    "--hermes-bin",
    hermes_bin,
    "--agent-name",
    agent_name,
    "--public-url",
    public_url,
    "--description",
    "User-facing Hermes Harness boss profile. Internal boss-team roles communicate through the local factory bus.",
]
with open(log, "wb") as out:
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
print(proc.pid)
PY
)"
echo "$pid" > "$HERMES_A2A_PID_DIR/$profile.pid"
echo "started user-facing $profile A2A endpoint pid=$pid log=$log"
echo "A2A public endpoint: http://${HERMES_A2A_PUBLIC_HOST:-127.0.0.1}:$port/"

echo "Only the public boss endpoint is exposed; internal profiles remain on the factory bus."
