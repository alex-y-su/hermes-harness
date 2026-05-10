#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
A2A_LOCK_FILE="${HERMES_A2A_LOCK_FILE:-$ROOT_DIR/hermes-a2a.lock.json}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_PYTHON="${HERMES_PYTHON:-$HERMES_HOME/hermes-agent/venv/bin/python}"
HERMES_A2A_BIN_DIR="${HERMES_A2A_BIN_DIR:-$HOME/.local/bin}"
HERMES_A2A_INSTALL_DIR="${HERMES_A2A_INSTALL_DIR:-$HOME/.local/share/hermes-a2a}"
HERMES_A2A_BASE_PORT="${HERMES_A2A_BASE_PORT:-8080}"
HERMES_A2A_PUBLIC_HOST="${HERMES_A2A_PUBLIC_HOST:-127.0.0.1}"
HERMES_A2A_BIND_HOST="${HERMES_A2A_BIND_HOST:-127.0.0.1}"
HERMES_A2A_MANIFEST="${HERMES_A2A_MANIFEST:-$HERMES_HOME/a2a-team.json}"
HERMES_A2A_PUBLIC_PROFILE="${HERMES_A2A_PUBLIC_PROFILE:-boss}"
HERMES_A2A_PUBLIC_AGENT_NAME="${HERMES_A2A_PUBLIC_AGENT_NAME:-boss}"

PROFILES=(boss supervisor hr conductor critic a2a-bridge)

read_lock() {
  python3 - "$A2A_LOCK_FILE" "$1" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data[sys.argv[2]])
PY
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
[ -x "$HERMES_PYTHON" ] || fail "Hermes Python not found at $HERMES_PYTHON; run scripts/bootstrap_hermes_agent.sh first"

bootstrap_url="$(read_lock bootstrap_script)"
pin_commit="$(read_lock commit)"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/hermes-a2a-install.XXXXXX")"
trap 'rm -rf "$tmp_dir"' EXIT

echo "Hermes A2A install"
echo "  home:    $HERMES_HOME"
echo "  commit:  $pin_commit"
echo "  bind:    $HERMES_A2A_BIND_HOST"
echo "  public:  $HERMES_A2A_PUBLIC_HOST"
echo "  facing:  $HERMES_A2A_PUBLIC_PROFILE"

curl -fsSL "$bootstrap_url" -o "$tmp_dir/a2a.sh"
HERMES_PYTHON="$HERMES_PYTHON" \
HERMES_A2A_REF="$pin_commit" \
HERMES_A2A_BIN_DIR="$HERMES_A2A_BIN_DIR" \
HERMES_A2A_INSTALL_DIR="$HERMES_A2A_INSTALL_DIR" \
bash "$tmp_dir/a2a.sh"

for index in "${!PROFILES[@]}"; do
  profile="${PROFILES[$index]}"
  profile_home="$HERMES_HOME/profiles/$profile"
  [ -f "$profile_home/config.yaml" ] || fail "Missing profile config: $profile_home/config.yaml"
  port="$((HERMES_A2A_BASE_PORT + index))"
  A2A_HOST="$HERMES_A2A_BIND_HOST" \
  A2A_PORT="$port" \
  A2A_PUBLIC_URL="http://$HERMES_A2A_PUBLIC_HOST:$port" \
  A2A_AGENT_NAME="$profile" \
  A2A_AGENT_DESCRIPTION="Hermes Harness boss-team profile: $profile" \
  A2A_REQUIRE_AUTH=true \
  HERMES_A2A_ROOT_HOME="$HERMES_HOME" \
  "$HERMES_A2A_BIN_DIR/hermes_a2a" install --hermes-home "$profile_home" --yes
done

"$HERMES_PYTHON" - "$HERMES_HOME" "$HERMES_A2A_MANIFEST" "$HERMES_A2A_PUBLIC_HOST" "$HERMES_A2A_BASE_PORT" "$HERMES_A2A_PUBLIC_PROFILE" "$HERMES_A2A_PUBLIC_AGENT_NAME" "${PROFILES[@]}" <<'PY'
import json
import sys
from pathlib import Path

import yaml

home = Path(sys.argv[1]).expanduser().resolve()
manifest_path = Path(sys.argv[2]).expanduser().resolve()
public_host = sys.argv[3]
base_port = int(sys.argv[4])
public_profile = sys.argv[5]
public_agent_name = sys.argv[6]
profiles = sys.argv[7:]

if public_profile not in profiles:
    raise SystemExit(f"public profile {public_profile!r} is not in {profiles!r}")

entries = []
for index, profile in enumerate(profiles):
    cfg_path = home / "profiles" / profile / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    a2a = cfg.get("a2a") or {}
    server = a2a.get("server") or {}
    token = str(server.get("auth_token") or "")
    port = base_port + index
    entries.append(
        {
            "profile": profile,
            "name": public_agent_name if profile == public_profile else profile,
            "url": f"http://{public_host}:{port}",
            "agent_card_url": f"http://{public_host}:{port}/.well-known/agent.json",
            "jsonrpc_url": f"http://{public_host}:{port}/",
            "auth_token": token,
            "public": profile == public_profile,
        }
    )

public_entry = next(entry for entry in entries if entry["profile"] == public_profile)
for entry in entries:
    cfg_path = home / "profiles" / entry["profile"] / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    a2a = cfg.setdefault("a2a", {})
    a2a["enabled"] = entry["profile"] == public_profile
    a2a["public"] = entry["profile"] == public_profile
    a2a["agents"] = []
    server = a2a.setdefault("server", {})
    server["host"] = str(server.get("host") or "127.0.0.1")
    server["port"] = int(str(entry["url"]).rsplit(":", 1)[1])
    server["public_url"] = entry["url"]
    identity = a2a.setdefault("identity", {})
    if entry["profile"] == public_profile:
        identity["name"] = public_agent_name
        identity["description"] = "User-facing Hermes Harness boss profile. Internal roles communicate through the local factory bus."
    else:
        identity["description"] = "Internal Hermes Harness boss-team profile; not exposed as a user-facing A2A agent."
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

manifest = {
    "public_agent": public_entry,
    "profiles": [public_entry],
    "internal_profiles": [
        {
            "profile": entry["profile"],
            "runtime": "daemon" if entry["profile"] == "a2a-bridge" else "llm",
            "public": False,
        }
        for entry in entries
        if entry["profile"] != public_profile
    ],
    "usage": {
        "agent_card": "curl -H 'Authorization: Bearer <auth_token>' <agent_card_url>",
        "message_send_method": "SendMessage",
        "boundary": "Only public_agent is user-facing; internal profiles communicate through factory/ and daemon tools.",
    },
}
manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"manifest": str(manifest_path), "public_agent": public_entry["profile"], "internal_profiles": [entry["profile"] for entry in entries if entry["profile"] != public_profile]}, indent=2))
PY

echo "Hermes A2A install complete."
