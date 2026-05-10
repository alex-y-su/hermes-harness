# Hermes Harness Boss Team Contract

This is the canonical local boss-team contract for Hermes Harness.

The boss team is generic and has exactly six profiles:

| Profile | Hub tenant ID | Runtime | Responsibility |
|---|---|---|---|
| `boss` | `boss` | LLM | Forms strategy and writes orders. |
| `supervisor` | `supervisor` | LLM | Signs in-envelope work and escalates novel work. |
| `hr` | `hr_profile` | LLM | Routes approved orders to remote teams and manages lifecycle. |
| `conductor` | `conductor` | LLM | Owns cron cadence, health checks, and throughput balance. |
| `critic` | `critic` | LLM | Reviews deliverables before boss-team acceptance. |
| `a2a-bridge` | `a2a_bridge` | daemon | Moves work between the factory bus and remote teams over A2A. |

Only these six profiles are installed on the hub machine. Specialist and execution roles are not local Hermes profiles. They are defined in `factory/team_blueprints/` as hireable remote-team blueprints, then `hr` creates actual hired-team state under `factory/teams/<name>/` and runs active work on E2B.

`hr` and `a2a-bridge` use different hub tenant IDs because the current hub API requires tenant IDs to match `^[a-z][a-z0-9_]{2,62}$`.

For official Hermes Agent installs, each profile home is installed at `~/.hermes/profiles/<profile>/`.
The legacy installer layout `~/.hermes-<profile>/` is still supported by `harness-boss-team --layout legacy`.

Each profile home contains:

- `AGENTS.md`
- `SOUL.md`
- `TEAM_SOUL.md`
- `config.yaml`

The shared profile config is:

```yaml
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
```

The contract is implemented in `harness/boss_team.py`. Use:

```bash
scripts/bootstrap_hermes_agent.sh
harness-boss-team install-local --factory "$FACTORY_DIR" --home-root "$HOME/.hermes" --layout hermes-profiles
harness-boss-team verify-local --factory "$FACTORY_DIR" --home-root "$HOME/.hermes" --layout hermes-profiles
harness-boss-team apply-hub --hub-url http://127.0.0.1:18080 --token "$HERMES_HUB_API_TOKEN"
harness-boss-team verify-hub --hub-url http://127.0.0.1:18080 --token "$HERMES_HUB_API_TOKEN"
```

The local install also writes the generic operating bus into the factory:

- `factory/PROTOCOL.md`, `factory/HARD_RULES.md`, `factory/STANDING_APPROVALS.md`
- `factory/wiki/` and `factory/sources/` domain-neutral memory scaffold
- `factory/team_blueprints/{growth,eng,brand,dev,research,ops}/`

To hire one of those remote teams:

```bash
python3 -m harness.tools.spawn_team \
  --factory /factory \
  --substrate e2b \
  --template multi-agent \
  --blueprint research \
  research
```

The spawned folder is hub-side state only. Runtime execution is per-assignment E2B through the bridge and A2A transport.

Hermes Agent itself is pinned by `hermes-agent.lock.json`. The bootstrap script uses the official Hermes installer from that pinned commit, checks the checkout out to the exact pinned commit, reinstalls the package in the Hermes virtualenv, configures OpenAI Codex OAuth from the local Codex auth file, and writes the boss-team profiles.

A2A HTTP support is installed through the pinned external `tickernelz/hermes-a2a` adapter in `hermes-a2a.lock.json`. `scripts/bootstrap_hermes_agent.sh` calls `scripts/install_hermes_a2a.sh`, which installs the adapter into each boss-team profile and emits `~/.hermes/a2a-team.json`.

Client communication is plain A2A JSON-RPC over HTTP. It does not require SSE or a socket-mode chat gateway. Only the `boss` profile is user-facing. `supervisor`, `hr`, `conductor`, `critic`, and `a2a-bridge` are internal roles that communicate through the local factory bus and daemon/tool calls. `scripts/start_hermes_a2a_team.sh` starts only the public boss endpoint using `harness-hermes-a2a-server`; that endpoint invokes the official pinned Hermes CLI with the `boss` profile and Codex OAuth provider. Start the local public A2A endpoint with:

```bash
scripts/start_hermes_a2a_team.sh
```

Then call the boss endpoint directly:

```bash
TOKEN="$(python3 - <<'PY'
import json, pathlib
data=json.loads(pathlib.Path('~/.hermes/a2a-team.json').expanduser().read_text())
print(data['public_agent']['auth_token'])
PY
)"

curl -X POST http://127.0.0.1:8080/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":{"kind":"message","role":"user","messageId":"msg-1","parts":[{"kind":"text","text":"Give me boss-team status."}]}}}'
```

The manifest's `profiles` list intentionally contains only the public boss endpoint. `internal_profiles` lists the other local roles for auditability without publishing their bearer tokens or URLs as user-facing agents.

For a plain host or VM deployment, use the native systemd installer instead of Docker:

```bash
HERMES_HOME=/opt/hermes-home \
FACTORY_DIR=/factory \
CODEX_HOME="$HOME/.codex" \
HERMES_A2A_PUBLIC_URL=https://a2a211.likeclaw.ai/ \
scripts/install_native_systemd.sh
```

That script installs the pinned official Hermes Agent checkout, imports Codex OAuth into every boss-team profile, writes the A2A manifest, and installs four host services: `hermes-boss-a2a`, `hermes-boss-gateway`, `hermes-bridge`, and `hermes-viewer`.

The Docker hub currently represents this contract as six tenants. The current hub schema does not store arbitrary role metadata, so the tenant identity is encoded through `id`, `displayName`, `publicHost`, and `auth.jwtSubjects`. It does not yet model the full local filesystem profile homes or cron registrations.
