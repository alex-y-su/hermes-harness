from __future__ import annotations

from harness.substrate.e2b import E2BDriver
from harness.substrate.external import ExternalSubstrateDriver


def build_driver(substrate: str, *, dry_run: bool = False, agent_card_url: str | None = None):
    if substrate == "external":
        return ExternalSubstrateDriver(agent_card_url=agent_card_url, dry_run=dry_run)
    if substrate == "e2b":
        return E2BDriver(dry_run=dry_run)
    raise ValueError(f"unsupported substrate: {substrate}")
