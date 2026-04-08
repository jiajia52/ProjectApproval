from __future__ import annotations

from typing import Any


def snapshot_endpoint_is_usable(endpoint: dict[str, Any] | None) -> bool:
    if not isinstance(endpoint, dict):
        return False
    return endpoint.get("ok") is True


def snapshot_has_usable_data(snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(snapshot, dict):
        return False
    endpoints = snapshot.get("endpoints") or {}
    return any(snapshot_endpoint_is_usable(item) for item in endpoints.values())


def merge_project_snapshots(primary: dict[str, Any] | None, fallback: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(primary, dict):
        return fallback or {"project_id": "", "endpoints": {}}
    if not isinstance(fallback, dict):
        return primary

    merged = {"project_id": primary.get("project_id") or fallback.get("project_id") or "", "endpoints": {}}
    primary_endpoints = primary.get("endpoints") or {}
    fallback_endpoints = fallback.get("endpoints") or {}
    for name in sorted(set(primary_endpoints) | set(fallback_endpoints)):
        primary_entry = primary_endpoints.get(name)
        fallback_entry = fallback_endpoints.get(name)
        merged["endpoints"][name] = primary_entry if snapshot_endpoint_is_usable(primary_entry) else fallback_entry
    return merged
