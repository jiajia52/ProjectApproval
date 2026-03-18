"""Persistence helpers for manual review feedback and AI review suggestions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path
from typing import Any

from app.core.paths import REVIEW_FEEDBACK_DIR

REVIEW_FEEDBACK_SCHEMA_VERSION = 1


def sanitize_name(value: str) -> str:
    sanitized = "".join(char if char.isascii() and (char.isalnum() or char in {"-", "_"}) else "_" for char in value).strip("_")
    if sanitized:
        return sanitized
    digest = md5(value.encode("utf-8")).hexdigest()[:12]
    return f"review_{digest}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def review_feedback_dir(project_id: str) -> Path:
    return REVIEW_FEEDBACK_DIR / sanitize_name(project_id)


def latest_review_feedback_path(project_id: str, category: str) -> Path:
    return review_feedback_dir(project_id) / f"latest_{sanitize_name(category)}.json"


def _flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    feedback = dict(record.get("feedback") or {})
    feedback["projectId"] = record.get("project_id") or ""
    feedback["projectName"] = record.get("project_name") or ""
    feedback["category"] = record.get("category") or ""
    feedback["savedAt"] = record.get("saved_at") or ""
    return feedback


def load_review_feedback(project_id: str, category: str) -> dict[str, Any] | None:
    path = latest_review_feedback_path(project_id, category)
    if not path.exists():
        return None
    record = read_json(path)
    if record.get("schema_version") != REVIEW_FEEDBACK_SCHEMA_VERSION:
        return None
    return _flatten_record(record)


def load_latest_review_feedback_map(category: str) -> dict[str, dict[str, Any]]:
    if not REVIEW_FEEDBACK_DIR.exists():
        return {}

    latest_items: dict[str, dict[str, Any]] = {}
    pattern = f"*/latest_{sanitize_name(category)}.json"
    for path in sorted(REVIEW_FEEDBACK_DIR.glob(pattern)):
        try:
            record = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("schema_version") != REVIEW_FEEDBACK_SCHEMA_VERSION:
            continue
        if str(record.get("category") or "") != category:
            continue
        project_id = str(record.get("project_id") or "").strip()
        if not project_id:
            continue
        latest_items[project_id] = _flatten_record(record)
    return latest_items


def persist_review_feedback(
    *,
    project_id: str,
    project_name: str,
    category: str,
    feedback: dict[str, Any],
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S-%f")
    saved_at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    record = {
        "schema_version": REVIEW_FEEDBACK_SCHEMA_VERSION,
        "project_id": project_id,
        "project_name": project_name,
        "category": category,
        "saved_at": saved_at,
        "feedback": feedback,
    }
    output_dir = review_feedback_dir(project_id)
    version_path = output_dir / f"{timestamp}_{sanitize_name(category)}.json"
    write_json(version_path, record)
    write_json(latest_review_feedback_path(project_id, category), record)
    return _flatten_record(record)
