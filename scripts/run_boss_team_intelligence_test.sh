#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${HERMES_BOSS_CONTAINER:-hermes-boss}"

exec docker exec \
  -e OPENAI_API_KEY= \
  -e OPENROUTER_API_KEY= \
  -e OPENROUTER_API_KEY_AIWIZ_LANDING= \
  -e LLM_BASE_URL= \
  "$CONTAINER" \
  env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u OPENROUTER_API_KEY_AIWIZ_LANDING -u LLM_BASE_URL \
  python3 -m harness.tools.boss_team_intelligence_test "$@"
