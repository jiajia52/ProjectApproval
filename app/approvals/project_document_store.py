"""Persisted project documents used by the UI and LLM approval flow."""

from __future__ import annotations

import json
from hashlib import md5
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.paths import LEGACY_PROJECT_DOCUMENTS_DIR, scene_project_documents_dir
from app.core.scenes import normalize_scene

PROJECT_DOCUMENT_SCHEMA_VERSION = 6


def sanitize_name(value: str) -> str:
    sanitized = "".join(char if char.isascii() and (char.isalnum() or char in {"-", "_"}) else "_" for char in value).strip("_")
    if sanitized:
        return sanitized
    digest = md5(value.encode("utf-8")).hexdigest()[:12]
    return f"document_{digest}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def project_document_dir(project_id: str, scene: str = "initiation") -> Path:
    return scene_project_documents_dir(scene) / sanitize_name(project_id)


def latest_document_path(project_id: str, category: str, scene: str = "initiation") -> Path:
    return project_document_dir(project_id, scene) / f"latest_{normalize_scene(scene)}_{sanitize_name(category)}.json"


def prune_project_document_history(output_dir: Path) -> None:
    try:
        paths = [path for path in output_dir.glob("*.json") if path.is_file()]
    except Exception:
        return
    for path in paths:
        if path.name.startswith("latest_"):
            continue
        try:
            path.unlink()
        except Exception:
            continue


def load_project_document(project_id: str, category: str, scene: str = "initiation") -> dict[str, Any] | None:
    path = latest_document_path(project_id, category, scene)
    if path.exists():
        record = read_json(path)
        if record.get("schema_version") == PROJECT_DOCUMENT_SCHEMA_VERSION:
            return record

    if normalize_scene(scene) == "initiation":
        legacy_project_dir = LEGACY_PROJECT_DOCUMENTS_DIR / sanitize_name(project_id)
        legacy_category_path = legacy_project_dir / f"latest_{sanitize_name(category)}.json"
        if legacy_category_path.exists():
            record = read_json(legacy_category_path)
            if record.get("schema_version") == PROJECT_DOCUMENT_SCHEMA_VERSION:
                return record

    if normalize_scene(scene) == "initiation":
        legacy_base_dir = LEGACY_PROJECT_DOCUMENTS_DIR / sanitize_name(project_id)
        legacy_path = legacy_base_dir / "latest_document.json"
        if legacy_path.exists():
            record = read_json(legacy_path)
            if record.get("schema_version") == PROJECT_DOCUMENT_SCHEMA_VERSION:
                return record
    return None


def persist_project_document(
    *,
    project_id: str,
    category: str,
    scene: str = "initiation",
    document: dict[str, Any],
    source: str,
    snapshot: dict[str, Any] | None = None,
    project_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S-%f")
    saved_at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    normalized_scene = normalize_scene(scene)
    record = {
        "schema_version": PROJECT_DOCUMENT_SCHEMA_VERSION,
        "project_id": project_id,
        "category": category,
        "scene": normalized_scene,
        "source": source,
        "saved_at": saved_at,
        "project_summary": project_summary or document.get("project_summary") or {},
        "snapshot": snapshot or document.get("remote_snapshot") or {"project_id": project_id, "endpoints": {}},
        "document": document,
    }
    output_dir = project_document_dir(project_id, normalized_scene)
    version_path = output_dir / f"{timestamp}_{normalized_scene}_{sanitize_name(category)}.json"
    write_json(version_path, record)
    write_json(latest_document_path(project_id, category, normalized_scene), record)
    prune_project_document_history(output_dir)
    return record
