from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hermes_harness.mock_x_api")
    sub = parser.add_subparsers(dest="command", required=True)

    post = sub.add_parser("post", help="Record a mock X post.")
    post.add_argument("--text", required=True)
    post.add_argument("--metadata", default="{}")
    post.add_argument("--json", action="store_true")

    list_cmd = sub.add_parser("list", help="List mock X posts.")
    list_cmd.add_argument("--json", action="store_true")

    return parser


def post(text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": f"mock-x-{uuid.uuid4().hex[:12]}",
        "text": text,
        "metadata": metadata or {},
        "created_at": _now(),
        "mock_external_api": "x",
    }
    path = _posts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return payload


def list_posts() -> list[dict[str, Any]]:
    path = _posts_path()
    if not path.exists():
        return []
    posts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            posts.append(json.loads(line))
    return posts


def _posts_path() -> Path:
    hermes_home = Path(os.environ.get("HERMES_HOME", "/vm/hermes-home"))
    return hermes_home / "mock-x" / "posts.jsonl"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "post":
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid --metadata JSON: {exc}") from exc
        payload = post(args.text, metadata=metadata)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(payload["id"])
        return 0
    if args.command == "list":
        posts = list_posts()
        if args.json:
            print(json.dumps(posts, indent=2, sort_keys=True))
        else:
            for item in posts:
                print(f"{item['id']}: {item['text']}")
        return 0
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
