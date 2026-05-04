from __future__ import annotations

import argparse
import os
from pathlib import Path

from harness.bridge.daemon import BridgeDaemon, install_signal_handlers
from harness.bridge.secrets import SecretResolver
from harness.bridge.store import BridgeDb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Hermes Harness A2A bridge")
    parser.add_argument("--factory", default=os.environ.get("HARNESS_FACTORY_DIR", "factory"))
    parser.add_argument("--db", default=os.environ.get("HARNESS_SQLITE_PATH", "bridge/hermes-harness.sqlite"))
    parser.add_argument("--env", default=os.environ.get("HARNESS_ENV_PATH"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HARNESS_A2A_BRIDGE_PORT", "8787")))
    parser.add_argument("--poll-ms", type=int, default=int(os.environ.get("HARNESS_A2A_BRIDGE_POLL_MS", "2000")))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.env:
        raise SystemExit("HARNESS_ENV_PATH must point to the external .env file")
    db = BridgeDb(Path(args.db))
    daemon = BridgeDaemon(
        factory_dir=Path(args.factory),
        db=db,
        secrets=SecretResolver(args.env),
        port=args.port,
        poll_ms=args.poll_ms,
    )
    install_signal_handlers(daemon, db)
    try:
        daemon.serve_forever()
    finally:
        daemon.stop()
        db.close()


if __name__ == "__main__":
    main()
