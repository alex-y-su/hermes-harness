from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RESOURCE_DIRNAME = "resources"


def resource_root(factory: Path) -> Path:
    return factory / RESOURCE_DIRNAME


def list_resources(factory: Path) -> list[dict[str, Any]]:
    root = resource_root(factory)
    if not root.exists():
        return []
    resources = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md"}:
            continue
        resources.append(_read_resource(root, path))
    return sorted(resources, key=lambda item: (str(item.get("state") or ""), str(item.get("id") or "")))


def get_resource(factory: Path, resource_id: str) -> dict[str, Any] | None:
    normalized = normalize_resource_id(resource_id)
    for resource in list_resources(factory):
        if normalize_resource_id(str(resource.get("id") or "")) == normalized:
            return resource
    return None


def resources_by_id(factory: Path) -> dict[str, dict[str, Any]]:
    return {normalize_resource_id(str(resource.get("id") or "")): resource for resource in list_resources(factory)}


def resource_refs_from_metadata(metadata: dict[str, Any] | None) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    values: list[Any] = []
    for key in ("resource", "resource_id", "target_resource", "target_resource_id"):
        if metadata.get(key):
            values.append(metadata[key])
    for key in ("resources", "resource_ids", "resource_dependencies", "dependencies"):
        if metadata.get(key):
            values.append(metadata[key])
    approval = metadata.get("approval") or metadata.get("approval_details") or metadata.get("decision")
    if isinstance(approval, dict):
        values.extend(resource_refs_from_metadata(approval))
    refs: list[str] = []
    for value in values:
        refs.extend(_flatten_resource_refs(value))
    deduped = []
    seen = set()
    for ref in refs:
        normalized = normalize_resource_id(ref)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def normalize_resource_id(value: str) -> str:
    return re.sub(r"/+", "/", value.strip().strip("/"))


def _read_resource(root: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    fallback_id = str(Path(rel).with_suffix(""))
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            data = {"id": fallback_id, "state": "invalid", "error": str(error)}
        if not isinstance(data, dict):
            data = {"id": fallback_id, "state": "invalid", "error": "resource JSON must be an object"}
        body = data.pop("body", "")
    else:
        data, body = _read_markdown_resource(path)
    data.setdefault("id", fallback_id)
    data.setdefault("title", data.get("name") or data["id"])
    data.setdefault("kind", data.get("type") or "resource")
    data.setdefault("state", data.get("status") or "unknown")
    data["id"] = normalize_resource_id(str(data["id"]))
    data["body"] = body
    data["path"] = str(path)
    data["relative_path"] = rel
    return data


def _read_markdown_resource(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    frontmatter = text[4:end].strip()
    body = text[end + 4 :].lstrip("\n")
    data: dict[str, Any] = {}
    for raw in frontmatter.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = _parse_scalar(value.strip())
    return data, body


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    if "," in value:
        return [part.strip() for part in value.split(",") if part.strip()]
    return value.strip('"').strip("'")


def _flatten_resource_refs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        refs: list[str] = []
        for key in ("id", "resource", "resource_id", "target_resource", "target_resource_id"):
            if value.get(key):
                refs.extend(_flatten_resource_refs(value[key]))
        if value.get("resources"):
            refs.extend(_flatten_resource_refs(value["resources"]))
        return refs
    if isinstance(value, list):
        refs: list[str] = []
        for item in value:
            refs.extend(_flatten_resource_refs(item))
        return refs
    return []
