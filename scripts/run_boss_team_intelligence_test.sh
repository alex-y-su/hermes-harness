#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "${HERMES_TEST_RUNTIME:-native}" = "docker" ]; then
  CONTAINER="${HERMES_BOSS_CONTAINER:-hermes-boss}"
  exec docker exec \
    -e OPENAI_API_KEY= \
    -e OPENROUTER_API_KEY= \
    -e OPENROUTER_API_KEY_AIWIZ_LANDING= \
    -e LLM_BASE_URL= \
    "$CONTAINER" \
    env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u OPENROUTER_API_KEY_AIWIZ_LANDING -u LLM_BASE_URL \
    python3 -m harness.tools.boss_team_intelligence_test "$@"
fi

PYTHON="${HERMES_TEST_PYTHON:-python3}"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u OPENROUTER_API_KEY_AIWIZ_LANDING -u LLM_BASE_URL \
  "$PYTHON" -m harness.tools.boss_team_intelligence_test "$@"
