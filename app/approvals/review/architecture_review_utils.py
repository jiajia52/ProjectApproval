from __future__ import annotations

from typing import Any


def normalize_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        for key in ["dataList", "list", "rows", "records", "items", "reviewResult", "dimensionList"]:
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def build_review_error_group(key: str, title: str, link_label: str, message: str) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "link_label": link_label,
        "ok": False,
        "message": message,
        "summary": {},
        "items": [],
    }


def snapshot_endpoint_payload(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    endpoints = snapshot.get("endpoints") or {}
    payload = endpoints.get(key)
    return payload if isinstance(payload, dict) else {}


def architecture_review_groups_have_material(groups: list[dict[str, Any]] | None) -> bool:
    if not isinstance(groups, list):
        return False
    for group in groups:
        if not isinstance(group, dict):
            continue
        if normalize_list(group.get("items")):
            return True
        group_key = str(group.get("key") or "").strip()
        summary = group.get("summary") or {}
        if not isinstance(summary, dict):
            continue
        if group_key == "data" and int(summary.get("check_point_count") or 0) > 0:
            return True
        if group_key in {"technology", "security"} and (
            int(summary.get("app_count") or 0) > 0 or int(summary.get("service_count") or 0) > 0
        ):
            return True
    return False


def review_groups_to_document_fields(groups: list[dict[str, Any]]) -> dict[str, Any]:
    field_map = {"business": "business", "data": "data", "technology": "technology", "security": "security"}
    architecture_reviews: dict[str, Any] = {}
    for group in groups:
        normalized_key = field_map.get(str(group.get("key") or "").strip())
        if not normalized_key:
            continue
        architecture_reviews[normalized_key] = {
            "summary": group.get("summary") or {},
            "items": group.get("items") or [],
            "message": str(group.get("message") or ""),
            "link_label": str(group.get("link_label") or ""),
        }
    return architecture_reviews
