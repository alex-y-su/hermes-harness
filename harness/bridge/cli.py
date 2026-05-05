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
    parser.add_argument("--e2b-dry-run", action="store_true", default=os.environ.get("HARNESS_E2B_DRY_RUN") == "1")
    parser.add_argument("--retry-delay-seconds", type=int, default=int(os.environ.get("HARNESS_ASSIGNMENT_RETRY_DELAY_SECONDS", "60")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("HARNESS_ASSIGNMENT_MAX_RETRIES", "3")))
    parser.add_argument("--assignment-lease-ttl-seconds", type=int, default=int(os.environ.get("HARNESS_ASSIGNMENT_LEASE_TTL_SECONDS", "300")))
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
        e2b_dry_run=args.e2b_dry_run,
        retry_delay_seconds=args.retry_delay_seconds,
        max_retries=args.max_retries,
        assignment_lease_ttl_seconds=args.assignment_lease_ttl_seconds,
    )
    install_signal_handlers(daemon, db)
    try:
        daemon.serve_forever()
    finally:
        daemon.stop()
        db.close()


if __name__ == "__main__":
    main()
