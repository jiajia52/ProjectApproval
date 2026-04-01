"""Persistence helpers for manual review feedback and AI review suggestions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path
from typing import Any

from app.core.paths import LEGACY_REVIEW_FEEDBACK_DIR, scene_review_feedback_dir
from app.core.scenes import normalize_scene

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


def review_feedback_dir(project_id: str, scene: str = "initiation") -> Path:
    return scene_review_feedback_dir(scene) / sanitize_name(project_id)


def latest_review_feedback_path(project_id: str, category: str, scene: str = "initiation") -> Path:
    return review_feedback_dir(project_id, scene) / f"latest_{normalize_scene(scene)}_{sanitize_name(category)}.json"


def _flatten_record(record: dict[str, Any], scene: str = "initiation") -> dict[str, Any]:
    feedback = dict(record.get("feedback") or {})
    feedback["projectId"] = record.get("project_id") or ""
    feedback["projectName"] = record.get("project_name") or ""
    feedback["category"] = record.get("category") or ""
    feedback["scene"] = record.get("scene") or normalize_scene(scene)
    feedback["savedAt"] = record.get("saved_at") or ""
    return feedback


def load_review_feedback(project_id: str, category: str, scene: str = "initiation") -> dict[str, Any] | None:
    path = latest_review_feedback_path(project_id, category, scene)
    if not path.exists():
        if normalize_scene(scene) != "initiation":
            return None
        path = (LEGACY_REVIEW_FEEDBACK_DIR / sanitize_name(project_id)) / f"latest_{sanitize_name(category)}.json"
        if not path.exists():
            return None
    record = read_json(path)
    if record.get("schema_version") != REVIEW_FEEDBACK_SCHEMA_VERSION:
        return None
    return _flatten_record(record, scene)


def load_latest_review_feedback_map(category: str, scene: str = "initiation") -> dict[str, dict[str, Any]]:
    active_dir = scene_review_feedback_dir(scene)
    if not active_dir.exists() and normalize_scene(scene) != "initiation":
        return {}

    latest_items: dict[str, dict[str, Any]] = {}
    normalized_scene = normalize_scene(scene)
    pattern = f"*/latest_{normalized_scene}_{sanitize_name(category)}.json"
    paths = sorted(active_dir.glob(pattern)) if active_dir.exists() else []
    if normalized_scene == "initiation":
        if active_dir.exists():
            paths.extend(sorted(active_dir.glob(f"*/latest_{sanitize_name(category)}.json")))
        if LEGACY_REVIEW_FEEDBACK_DIR.exists():
            paths.extend(sorted(LEGACY_REVIEW_FEEDBACK_DIR.glob(pattern)))
            paths.extend(sorted(LEGACY_REVIEW_FEEDBACK_DIR.glob(f"*/latest_{sanitize_name(category)}.json")))

    for path in paths:
        try:
            record = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("schema_version") != REVIEW_FEEDBACK_SCHEMA_VERSION:
            continue
        record_scene = normalize_scene(record.get("scene") or "initiation")
        if record_scene != normalized_scene:
            continue
        if str(record.get("category") or "") != category:
            continue
        project_id = str(record.get("project_id") or "").strip()
        if not project_id:
            continue
        latest_items[project_id] = _flatten_record(record, scene)
    return latest_items


def persist_review_feedback(
    *,
    project_id: str,
    project_name: str,
    category: str,
    scene: str = "initiation",
    feedback: dict[str, Any],
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S-%f")
    saved_at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    normalized_scene = normalize_scene(scene)
    record = {
        "schema_version": REVIEW_FEEDBACK_SCHEMA_VERSION,
        "project_id": project_id,
        "project_name": project_name,
        "category": category,
        "scene": normalized_scene,
        "saved_at": saved_at,
        "feedback": feedback,
    }
    output_dir = review_feedback_dir(project_id, normalized_scene)
    version_path = output_dir / f"{timestamp}_{normalized_scene}_{sanitize_name(category)}.json"
    write_json(version_path, record)
    write_json(latest_review_feedback_path(project_id, category, normalized_scene), record)
    return _flatten_record(record, normalized_scene)
