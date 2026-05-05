#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FACTORY_DIR="${FACTORY_DIR:-/factory}"
HERMES_HOME="${HERMES_HOME:-/opt/hermes-home}"
HERMES_BIN="${HERMES_BIN:-/home/dev/.local/bin/hermes}"
CONFIG_SCRIPT="${CONFIG_SCRIPT:-$ROOT_DIR/scripts/factory_config_versions.sh}"
LABEL="${LABEL:-24-7-controlled-activation}"
PUBLIC_PUSH_URL="${PUBLIC_PUSH_URL:-https://a2a211.likeclaw.ai/a2a/push}"
RUN_ONCE="${RUN_ONCE:-0}"
INSTALL_SYSTEMD="${INSTALL_SYSTEMD:-1}"
SERVICE_USER="${SERVICE_USER:-dev}"
SYSTEMD_ENV_FILE="${SYSTEMD_ENV_FILE:-/etc/hermes-harness/native.env}"

export FACTORY_DIR HERMES_HOME HARNESS_FACTORY="$FACTORY_DIR"
unset OPENAI_API_KEY OPENROUTER_API_KEY OPENROUTER_API_KEY_AIWIZ_LANDING LLM_BASE_URL

if [ ! -x "$HERMES_BIN" ]; then
  echo "missing Hermes binary: $HERMES_BIN" >&2
  exit 1
fi

if [ ! -x "$CONFIG_SCRIPT" ]; then
  echo "missing config version script: $CONFIG_SCRIPT" >&2
  exit 1
fi

"$CONFIG_SCRIPT" new "$LABEL" >/dev/null

cat >"$FACTORY_DIR/GOALS.md" <<'EOF_GOALS'
# GOALS.md

## 24/7 Controlled Proactive Company
- objective: continuously improve Hermes Harness as a proactive company, using the root boss team to observe, plan, approve, route, execute, review, and learn.
- root_team:
  - boss: forms strategy and writes bounded internal orders.
  - supervisor: approves in-envelope work and escalates novel or unsafe work.
  - hr: routes approved orders to existing remote teams or hires documented blueprints.
  - conductor: monitors cadence, failures, stale teams, and retry budgets.
  - critic: reviews returned artifacts against team criteria before acceptance.
  - a2a-bridge: dispatches remote assignments and records signed push updates.
- allowed_blueprints:
  - growth
  - eng
  - brand
  - room-engine
  - video
  - distro
  - sermons
  - creators
  - dev
  - churches
- constraints:
  - no external outreach without explicit user approval or standing approval.
  - no paid expansion beyond configured Hermes/Codex/E2B test budget without user approval.
  - no credential requests unless required to unblock a specific approved order.
  - no secrets edits from agent jobs.
  - no direct runtime DB edits from LLM jobs.
  - no infinite retry loops; repeated identical failures require backoff and a status artifact.
EOF_GOALS

cat >"$FACTORY_DIR/AUTOPILOT.md" <<'EOF_AUTOPILOT'
# AUTOPILOT.md

mode: active-controlled
cadence: recurring-root-team
activation_started_at: generated-by-activate-24-7-script

guardrails:
- root profile jobs may run continuously.
- remote team work must be routed through approved orders and A2A bridge.
- external outreach, account changes, budget increases, and credential requests must escalate to user.
- agents may create internal orders, approvals, assignments, status files, reviews, and local team folders.
- agents must prefer one useful next action per cycle over bulk spawning.
- conductor must surface repeated bridge, E2B, or auth failures instead of allowing tight retry loops.

agenda:
- boss observes state and writes at most three high-leverage internal orders per cycle.
- supervisor signs in-envelope work or writes a denial/escalation.
- hr routes approved orders and keeps the team roster usable.
- conductor writes health/cadence summaries and proposes backoff or cleanup.
- critic reviews new remote-team artifacts and writes approve/revise decisions.
EOF_AUTOPILOT

mkdir -p \
  "$HERMES_HOME/profiles/boss/scripts" \
  "$HERMES_HOME/profiles/supervisor/scripts" \
  "$HERMES_HOME/profiles/hr/scripts" \
  "$HERMES_HOME/profiles/conductor/scripts" \
  "$HERMES_HOME/profiles/critic/scripts"

cat >"$HERMES_HOME/profiles/boss/scripts/root_boss_pulse.py" <<'PY_BOSS'
#!/usr/bin/env python3
import json, os, pathlib, sqlite3, subprocess
F = pathlib.Path(os.environ.get("FACTORY_DIR", "/factory"))
def read(path, limit=5000):
    p = F / path
    return p.read_text(errors="replace")[:limit] if p.exists() else "(missing)"
def files(path, limit=20):
    p = F / path
    return [x.name for x in sorted(p.glob("*"))[:limit]] if p.exists() else []
print("=== root boss pulse snapshot ===")
for name in ["GOALS.md", "AUTOPILOT.md", "PRIORITIZE.md", "HARD_RULES.md", "STANDING_APPROVALS.md"]:
    print(f"--- {name} ---\n{read(name, 3000)}")
for d in ["orders", "approved_orders", "assignments", "escalations", "status", "teams"]:
    print(f"--- {d} ---\n{json.dumps(files(d, 40), indent=2)}")
try:
    out = subprocess.check_output(["python3", "-m", "harness.tools.query_remote_teams", "--factory", str(F), "--json"], cwd="/opt/hermes-harness", text=True, stderr=subprocess.STDOUT, timeout=20)
    print("--- query_remote_teams ---")
    print(out[:5000])
except Exception as exc:
    print(f"query_remote_teams failed: {exc}")
PY_BOSS

cat >"$HERMES_HOME/profiles/supervisor/scripts/root_supervisor_pulse.py" <<'PY_SUPERVISOR'
#!/usr/bin/env python3
import json, os, pathlib
F = pathlib.Path(os.environ.get("FACTORY_DIR", "/factory"))
def read(path, limit=4000):
    p = pathlib.Path(path)
    return p.read_text(errors="replace")[:limit] if p.exists() else "(missing)"
def recent(dir_name, limit=10):
    d = F / dir_name
    return [str(p) for p in sorted(d.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]] if d.exists() else []
print("=== supervisor approval snapshot ===")
print("--- hard rules ---")
print(read(F / "HARD_RULES.md", 3000))
print("--- standing approvals ---")
print(read(F / "STANDING_APPROVALS.md", 4000))
for d in ["orders", "approved_orders", "denials", "escalations"]:
    print(f"--- {d} ---")
    for path in recent(d):
        print(path)
        print(read(path, 2500))
PY_SUPERVISOR

cat >"$HERMES_HOME/profiles/hr/scripts/root_hr_pulse.py" <<'PY_HR'
#!/usr/bin/env python3
import json, os, pathlib, subprocess
F = pathlib.Path(os.environ.get("FACTORY_DIR", "/factory"))
def read(path, limit=3000):
    p = pathlib.Path(path)
    return p.read_text(errors="replace")[:limit] if p.exists() else "(missing)"
print("=== hr routing snapshot ===")
for d in ["approved_orders", "assignments", "team_blueprints", "teams", "escalations"]:
    root = F / d
    print(f"--- {d} ---")
    if root.exists():
        for p in sorted(root.iterdir())[:80]:
            print(p.name)
try:
    out = subprocess.check_output(["python3", "-m", "harness.tools.query_remote_teams", "--factory", str(F), "--json"], cwd="/opt/hermes-harness", text=True, stderr=subprocess.STDOUT, timeout=20)
    print("--- query_remote_teams ---")
    print(out[:6000])
except Exception as exc:
    print(f"query_remote_teams failed: {exc}")
PY_HR

cat >"$HERMES_HOME/profiles/conductor/scripts/root_conductor_pulse.py" <<'PY_CONDUCTOR'
#!/usr/bin/env python3
import json, os, pathlib, sqlite3, time
F = pathlib.Path(os.environ.get("FACTORY_DIR", "/factory"))
DB = F / "harness.sqlite3"
print("=== conductor health snapshot ===")
for path in ["status/a2a-bridge.json", "status/reliability-pulse.json"]:
    p = F / path
    print(f"--- {path} ---")
    print(p.read_text(errors="replace")[:3000] if p.exists() else "(missing)")
for d in ["orders", "approved_orders", "assignments", "teams"]:
    p = F / d
    count = len([x for x in p.iterdir() if not x.name.startswith(".")]) if p.exists() else 0
    print(f"{d}_count={count}")
if DB.exists():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    print("--- recent failures ---")
    for row in con.execute("select team_name, kind, state, count(*) as n, max(ts) as last_ts from team_events where state='failed' group by team_name, kind, state order by n desc limit 20"):
        print(dict(row))
PY_CONDUCTOR

cat >"$HERMES_HOME/profiles/critic/scripts/root_critic_pulse.py" <<'PY_CRITIC'
#!/usr/bin/env python3
import os, pathlib
F = pathlib.Path(os.environ.get("FACTORY_DIR", "/factory"))
print("=== critic review snapshot ===")
teams = sorted((F / "teams").iterdir()) if (F / "teams").exists() else []
for team in teams:
    outbox = team / "outbox"
    criteria = team / "criteria.md"
    if not outbox.exists():
        continue
    artifacts = [p for p in sorted(outbox.glob("*")) if p.is_file() and not p.name.startswith(".")]
    if not artifacts:
        continue
    print(f"--- team {team.name} criteria ---")
    print(criteria.read_text(errors="replace")[:2500] if criteria.exists() else "(missing)")
    print(f"--- team {team.name} artifacts ---")
    for artifact in artifacts[-10:]:
        print(f"FILE {artifact}")
        print(artifact.read_text(errors="replace")[:3000])
PY_CRITIC

chmod +x "$HERMES_HOME"/profiles/*/scripts/root_*_pulse.py

install_profile_gateway_services() {
  if [ "$INSTALL_SYSTEMD" != "1" ] || ! command -v systemctl >/dev/null 2>&1; then
    return
  fi
  for profile in supervisor hr conductor critic; do
    sudo tee "/etc/systemd/system/hermes-${profile}-gateway.service" >/dev/null <<EOF_SERVICE
[Unit]
Description=Hermes Harness ${profile} Hermes gateway and cron runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${ROOT_DIR}
EnvironmentFile=${SYSTEMD_ENV_FILE}
UnsetEnvironment=OPENAI_API_KEY OPENROUTER_API_KEY OPENROUTER_API_KEY_AIWIZ_LANDING LLM_BASE_URL
ExecStart=${HERMES_BIN} --profile ${profile} gateway run --accept-hooks
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF_SERVICE
  done
  sudo systemctl daemon-reload
  sudo systemctl enable --now hermes-supervisor-gateway hermes-hr-gateway hermes-conductor-gateway hermes-critic-gateway
}

install_profile_gateway_services

cron_names() {
  "$HERMES_BIN" --profile "$1" cron list 2>&1 | sed -n 's/^[[:space:]]*Name:[[:space:]]*//p'
}

ensure_job() {
  local profile="$1" name="$2" schedule="$3" script="$4" prompt="$5"
  if cron_names "$profile" | grep -Fxq "$name"; then
    echo "exists: $profile/$name"
    return
  fi
  "$HERMES_BIN" --profile "$profile" cron create "$schedule" "$prompt" \
    --name "$name" \
    --deliver local \
    --script "$script" \
    --workdir "$ROOT_DIR"
}

ensure_job boss "root-boss-strategic-pulse" "every 30m" "root_boss_pulse.py" \
"You are boss, strategic CEO of the Hermes Harness root team. Use the snapshot. In active-controlled mode, write at most three internal orders under /factory/orders for high-leverage work toward GOALS. Do not do external outreach, secrets edits, runtime DB edits, or remote dispatch directly. If no useful action is needed, write /factory/status/boss-pulse.json with a concise no-op reason."

ensure_job supervisor "root-supervisor-approval-pulse" "every 15m" "root_supervisor_pulse.py" \
"You are supervisor. Review new /factory/orders against HARD_RULES and STANDING_APPROVALS. Sign and move only in-envelope work to /factory/approved_orders. For novel/unsafe work, write a denial or escalation. Do not edit secrets or runtime DB."

ensure_job hr "root-hr-routing-pulse" "every 15m" "root_hr_pulse.py" \
"You are hr. Route approved orders to existing teams or hire documented blueprints only when the approved order explicitly asks for it. Write assignments through the harness tools/factory bus. Keep team roster usable. Do not create external outreach or credentials work."

ensure_job conductor "root-conductor-health-pulse" "every 15m" "root_conductor_pulse.py" \
"You are conductor. Monitor cadence, stale teams, bridge failures, and queue depth. Write /factory/status/conductor-health.json and, for repeated failures, create at most one internal guardrail order. Do not dispatch remote work directly."

ensure_job critic "root-critic-review-pulse" "every 20m" "root_critic_pulse.py" \
"You are critic. Review new team outbox artifacts against each team's criteria. Write review artifacts under /factory/outbox/critic or /factory/status/critic-review.json. Do not mutate team deliverables directly."

if [ "$RUN_ONCE" = "1" ]; then
  for profile in boss supervisor hr conductor critic; do
    echo "registered jobs for $profile:"
    "$HERMES_BIN" --profile "$profile" cron list | sed -n '1,160p'
  done
fi

echo "24/7 root team activation installed"
echo "factory=$FACTORY_DIR"
echo "config=$("$CONFIG_SCRIPT" status | sed -n 's/^current: //p')"
