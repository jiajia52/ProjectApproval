"""Persisted project documents used by the UI and LLM approval flow."""

from __future__ import annotations

import json
from hashlib import md5
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.paths import PROJECT_DOCUMENTS_DIR

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


def project_document_dir(project_id: str) -> Path:
    return PROJECT_DOCUMENTS_DIR / sanitize_name(project_id)


def latest_document_path(project_id: str, category: str) -> Path:
    return project_document_dir(project_id) / f"latest_{sanitize_name(category)}.json"


def load_project_document(project_id: str, category: str) -> dict[str, Any] | None:
    path = latest_document_path(project_id, category)
    if path.exists():
        record = read_json(path)
        if record.get("schema_version") == PROJECT_DOCUMENT_SCHEMA_VERSION:
            return record

    legacy_path = project_document_dir(project_id) / "latest_document.json"
    if legacy_path.exists():
        record = read_json(legacy_path)
        if record.get("schema_version") == PROJECT_DOCUMENT_SCHEMA_VERSION:
            return record
    return None


def persist_project_document(
    *,
    project_id: str,
    category: str,
    document: dict[str, Any],
    source: str,
    snapshot: dict[str, Any] | None = None,
    project_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S-%f")
    saved_at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    record = {
        "schema_version": PROJECT_DOCUMENT_SCHEMA_VERSION,
        "project_id": project_id,
        "category": category,
        "source": source,
        "saved_at": saved_at,
        "project_summary": project_summary or document.get("project_summary") or {},
        "snapshot": snapshot or document.get("remote_snapshot") or {"project_id": project_id, "endpoints": {}},
        "document": document,
    }
    output_dir = project_document_dir(project_id)
    version_path = output_dir / f"{timestamp}_{sanitize_name(category)}.json"
    write_json(version_path, record)
    write_json(latest_document_path(project_id, category), record)
    return record
