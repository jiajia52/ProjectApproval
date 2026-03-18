"""Summarize dumped API responses so the LLM can reason over observed response shapes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.paths import API_DUMPS_DIR


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_shape(base: dict[str, Any], value: Any, *, depth: int = 0, max_depth: int = 4) -> dict[str, Any]:
    result = dict(base)
    result.setdefault("types", [])
    type_name = type(value).__name__
    if type_name not in result["types"]:
        result["types"].append(type_name)

    if depth >= max_depth:
        return result

    if isinstance(value, dict):
        fields = dict(result.get("fields", {}))
        for key, nested in value.items():
            fields[key] = merge_shape(fields.get(key, {}), nested, depth=depth + 1, max_depth=max_depth)
        result["fields"] = fields
    elif isinstance(value, list):
        if value:
            item_shape = dict(result.get("items", {}))
            for item in value[:5]:
                item_shape = merge_shape(item_shape, item, depth=depth + 1, max_depth=max_depth)
            result["items"] = item_shape
        result["sample_size"] = max(result.get("sample_size", 0), len(value))

    return result


def iter_legacy_response_paths(active_root: Path) -> list[Path]:
    paths = set(active_root.glob("*/*/*.response.json"))
    paths.update(active_root.glob("*/*.response.json"))
    return sorted(path for path in paths if path.is_file())


def iter_project_bundle_paths(active_root: Path) -> list[Path]:
    paths = set(active_root.glob("projects/*.json"))
    paths.update(active_root.glob("*/projects/*.json"))
    return sorted(path for path in paths if path.is_file())


def build_structure_summary(root: Path | None = None) -> dict[str, Any]:
    active_root = root or API_DUMPS_DIR
    summary: dict[str, Any] = {"source_dir": str(active_root), "endpoints": {}}
    if not active_root.exists():
        return summary

    for response_path in iter_legacy_response_paths(active_root):
        endpoint_name = response_path.name.replace(".response.json", "")
        endpoint_summary = dict(summary["endpoints"].get(endpoint_name, {}))
        endpoint_summary = merge_shape(endpoint_summary, read_json(response_path))
        endpoint_summary["sample_count"] = endpoint_summary.get("sample_count", 0) + 1
        summary["endpoints"][endpoint_name] = endpoint_summary

    for bundle_path in iter_project_bundle_paths(active_root):
        payload = read_json(bundle_path)
        endpoints = payload.get("endpoints") or {}
        if not isinstance(endpoints, dict):
            continue
        for endpoint_name, endpoint_payload in endpoints.items():
            if not isinstance(endpoint_payload, dict):
                continue
            response = endpoint_payload.get("response")
            if response is None:
                continue
            endpoint_summary = dict(summary["endpoints"].get(endpoint_name, {}))
            endpoint_summary = merge_shape(endpoint_summary, response)
            endpoint_summary["sample_count"] = endpoint_summary.get("sample_count", 0) + 1
            summary["endpoints"][endpoint_name] = endpoint_summary

    return summary
