# Hermes Harness A2A Bridge

Runnable daemon:

```sh
HARNESS_FACTORY_DIR=/path/to/factory \
HARNESS_SQLITE_PATH=/path/to/hermes-harness.sqlite \
HARNESS_ENV_PATH=/path/outside/factory/harness.env \
HARNESS_A2A_BRIDGE_PORT=8787 \
harness-a2a-bridge
```

The Python daemon scans `factory/teams/*/inbox` for assignment markdown, receives `POST /a2a/push`, writes `factory/status/a2a-bridge.json`, and stops when `factory/HALT_a2a-bridge.flag` exists.

`transport.json` must contain secret references only. The referenced variables are resolved from `HARNESS_ENV_PATH`.
