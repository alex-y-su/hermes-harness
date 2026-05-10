# hermes-harness-remote-full

Base E2B template for Hermes Harness assignment sandboxes.

The template bakes slow, stable dependencies. Team identity, assignment data,
allowed runtime env, and team-specific files are synced per assignment by the
local E2B driver.

Build or rebuild the alias expected by `E2BDriver`:

```bash
env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u OPENROUTER_API_KEY_AIWIZ_LANDING -u LLM_BASE_URL npm install
env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u OPENROUTER_API_KEY_AIWIZ_LANDING -u LLM_BASE_URL npm run build:prod
```

The E2B CLI is pinned in `package.json`; the resulting template alias is
`hermes-harness-remote-full`.
