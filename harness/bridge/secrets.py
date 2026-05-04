from __future__ import annotations

import os
from pathlib import Path


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key.replace("_", "A").isalnum() or not (key[0].isalpha() or key[0] == "_"):
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value.replace("\\n", "\n")
    return values


class SecretResolver:
    def __init__(self, env_path: str | Path | None) -> None:
        self.env_path = Path(env_path) if env_path else None
        self.values = parse_dotenv(self.env_path.read_text(encoding="utf-8")) if self.env_path else {}

    def resolve(self, ref: str | None) -> str | None:
        if not ref:
            return None
        if not ref.startswith("env://"):
            raise ValueError(f"Unsupported secret ref: {ref}")
        key = ref.removeprefix("env://")
        value = self.values.get(key) or os.environ.get(key)
        if not value:
            raise ValueError(f"Missing secret for {ref}")
        return value
