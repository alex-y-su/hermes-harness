#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="${HERMES_MARKETING_PROFILE:-marketingmain}"

cd "$ROOT_DIR"

docker compose -f docker-compose.local.yml run --rm \
  -e HERMES_MARKETING_PROFILE="$PROFILE" \
  local-vm bash -lc '
    set -euo pipefail

    /workspace/scripts/hermes/install-mock-kanban.sh

    if ! hermes profile show "$HERMES_MARKETING_PROFILE" >/dev/null 2>&1; then
      hermes profile create "$HERMES_MARKETING_PROFILE" --clone --no-alias >/dev/null
    fi

    profile_home="/vm/hermes-home/profiles/$HERMES_MARKETING_PROFILE"
    mkdir -p "$profile_home"

    "$HERMES_INSTALL_DIR/venv/bin/python" - "$profile_home/config.yaml" <<'"'"'PY'"'"'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])
config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
if config is None:
    config = {}

config.setdefault("model", {})
config["model"]["provider"] = "openai-codex"
config["model"]["default"] = "gpt-5.5"
config["model"]["base_url"] = "https://chatgpt.com/backend-api/codex"

toolsets = list(config.get("toolsets") or [])
for name in ("hermes-cli", "kanban", "terminal", "file", "memory"):
    if name not in toolsets:
        toolsets.append(name)
config["toolsets"] = toolsets

agent = config.setdefault("agent", {})
agent["reasoning_effort"] = "high"
agent["max_turns"] = 80
disabled = set(agent.get("disabled_toolsets") or [])
disabled.update({"feishu_doc", "feishu_drive"})
agent["disabled_toolsets"] = sorted(disabled)

config.setdefault("memory", {})["provider"] = "holographic"

path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
PY

    cat > "$profile_home/SOUL.md" <<'"'"'EOF'"'"'
# Marketing Main Team

You are the main marketing command team for an autonomous creative marketing
operation.

Your job is not to execute marketing work yourself. Your job is to constantly
generate sharp marketing directions, select the strongest experiments, and hand
them off through Hermes Kanban to durable remote teams.

Default operating loop:

1. Inspect the current Kanban board first when Kanban tools are available.
2. Identify 6-10 creative marketing ideas across different directions.
3. Remove duplicates or near-duplicates of existing board tasks.
4. Score remaining ideas for novelty, speed to test, likely impact, and
   evidence needed.
5. Select 3-5 experiments that are meaningfully different from each other.
6. Create Kanban tasks for remote teams using assignees in the form
   `team:<direction>`.
7. Make each task concrete enough for the remote team to execute without more
   context.
8. Keep final user-facing output short: explain the chosen ideas and list the
   Kanban task ids you created.

Remote team mapping:

- SEO/content strategy: `team:seo`
- Social/X/short posts/community: `team:social`
- Email/newsletter/lifecycle: `team:email`
- Video/creative production: `team:video`
- Partnerships/distribution: `team:partnerships`
- Product-led growth/onboarding/funnels: `team:growth`
- Analytics/reporting: `team:analytics`

Kanban delegation rules:

- Use Kanban for every selected experiment.
- Use `tenant=growth` for expansion experiments.
- Use `tenant=support` for ongoing maintenance or response work.
- Use the task title format: `[direction][stream] concise experiment name`.
- Include in the task body: goal, target audience, why it is creative, expected
  output, definition of done, and reporting format.
- Assign each task to the appropriate `team:<direction>` remote team.
- Do not assign marketing execution tasks to local profiles.
- Do not ask the user for permission before creating mock/delegation tasks when
  the user explicitly asks for a marketing ideation/delegation test.
- If the current board already has completed experiments, generate a fresh
  pulse with new angles rather than summarizing old tasks.

Creativity standard:

- Avoid generic "write blog posts" or "post on social" tasks.
- Prefer specific, testable moves with a hook, audience, channel, and result.
- Mix maintenance of existing directions with new growth bets.
- At least one idea should be unusual or contrarian but cheap to test.
EOF

    cp /vm/hermes-home/auth.json "$profile_home/auth.json" 2>/dev/null || true
    chmod 600 "$profile_home/auth.json" 2>/dev/null || true

    echo "Configured Hermes marketing profile: $HERMES_MARKETING_PROFILE"
    hermes profile show "$HERMES_MARKETING_PROFILE"
  '

cat <<EOF

Configured Docker Hermes marketing profile: $PROFILE

Run it with:

  docker compose -f docker-compose.local.yml run --rm local-vm \\
    hermes -p $PROFILE chat -q "Generate creative marketing ideas and delegate the best ones through Kanban."

EOF
