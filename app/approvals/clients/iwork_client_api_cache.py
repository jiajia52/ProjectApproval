from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.parse
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config.paths import LEGACY_API_RESULT_DIR, scene_api_result_dir
from app.core.config.scenes import normalize_scene

LOGGER = logging.getLogger("project_approval.iwork_client")

_SNAPSHOT_CACHE_LOCK = threading.Lock()
_SNAPSHOT_CACHE: dict[str, dict[str, Any]] = {}
_PROJECT_PARAM_CACHE_LOCK = threading.Lock()
_PROJECT_PARAM_CACHE: dict[int, dict[str, Any]] = {}
_TASK_ORDER_STATUS_CACHE_LOCK = threading.Lock()
_TASK_ORDER_STATUS_CACHE: dict[str, Any] = {}
_ACCEPTANCE_REVIEW_PROJECTS_CACHE_LOCK = threading.Lock()
_ACCEPTANCE_REVIEW_PROJECTS_CACHE: dict[str, dict[str, Any]] = {}
_ACCEPTANCE_REVIEW_PROJECTS_CACHE_VERSION = 1


def read_json(path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_file_stem(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "api"


def prune_api_result_history(output_dir: Path, api_name: str, keep_filename: str) -> None:
    pattern = f"*_{sanitize_file_stem(api_name)}.json"
    try:
        matched_paths = [path for path in output_dir.glob(pattern) if path.is_file()]
    except Exception:
        return
    for stale_path in matched_paths:
        if stale_path.name == keep_filename:
            continue
        try:
            stale_path.unlink()
        except Exception:
            continue


def write_api_result(
    *,
    api_name: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    scene: str = "initiation",
    project_id: str | None = None,
    result: Any = None,
    error: str | None = None,
) -> Path:
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S-%f")
    output_dir = scene_api_result_dir(scene)
    normalized_project_id = sanitize_file_stem(str(project_id or "").strip()) if project_id else ""
    if normalized_project_id:
        output_dir = output_dir / "projects" / normalized_project_id
    output_path = output_dir / f"{timestamp}_{sanitize_file_stem(api_name)}.json"
    record = {
        "api_name": api_name,
        "method": method.upper(),
        "path": path,
        "payload": payload,
        "project_id": project_id or "",
        "result": result,
        "error": error or "",
        "called_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
    }
    write_json(output_path, record)
    prune_api_result_history(output_dir, api_name, output_path.name)
    return output_path


def api_result_search_dirs(scene: str = "initiation") -> list[Path]:
    normalized_scene = normalize_scene(scene)
    directories = [scene_api_result_dir(normalized_scene)]
    if normalized_scene == "initiation":
        directories.append(LEGACY_API_RESULT_DIR)
    return directories


def project_param_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_PARAM_CACHE_TTL", "600") or "600").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 600
    return max(0, min(ttl, 3600))


def acceptance_review_projects_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_ACCEPTANCE_REVIEW_LIST_CACHE_TTL", "120") or "120").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 120
    return max(0, min(ttl, 1800))


def _acceptance_review_projects_cache_key(status_codes: list[str]) -> str:
    normalized = [str(code or "").strip() for code in status_codes if str(code or "").strip()]
    return ",".join(normalized) or "4,9"


def load_cached_acceptance_review_projects(status_codes: list[str], *, allow_stale: bool = False) -> dict[str, Any] | None:
    cache_key = _acceptance_review_projects_cache_key(status_codes)
    ttl_seconds = acceptance_review_projects_cache_ttl_seconds()
    now = time.monotonic()
    if ttl_seconds > 0:
        with _ACCEPTANCE_REVIEW_PROJECTS_CACHE_LOCK:
            cached = _ACCEPTANCE_REVIEW_PROJECTS_CACHE.get(cache_key)
            if cached and float(cached.get("expires_at") or 0) > now:
                payload = cached.get("payload")
                if isinstance(payload, dict):
                    return deepcopy(payload)
            if cached:
                _ACCEPTANCE_REVIEW_PROJECTS_CACHE.pop(cache_key, None)

    api_name = f"acceptance_review_projects_cache_{cache_key.replace(',', '_')}"
    candidates: list[tuple[float, dict[str, Any]]] = []
    for search_dir in api_result_search_dirs("acceptance"):
        if not search_dir.exists():
            continue
        for path in search_dir.glob(f"*_{sanitize_file_stem(api_name)}.json"):
            try:
                record = read_json(path)
                payload = record.get("result")
                if not isinstance(payload, dict):
                    continue
                if int(payload.get("cache_version") or 0) != _ACCEPTANCE_REVIEW_PROJECTS_CACHE_VERSION:
                    continue
                modified_time = path.stat().st_mtime
            except Exception:
                continue
            candidates.append((modified_time, payload))

    if not candidates:
        return None

    modified_time, payload = max(candidates, key=lambda item: item[0])
    if ttl_seconds > 0 and not allow_stale and modified_time + ttl_seconds < time.time():
        return None
    cached_payload = deepcopy(payload)
    cached_payload["source"] = "cache"
    if ttl_seconds > 0:
        with _ACCEPTANCE_REVIEW_PROJECTS_CACHE_LOCK:
            _ACCEPTANCE_REVIEW_PROJECTS_CACHE[cache_key] = {
                "expires_at": now + ttl_seconds,
                "payload": deepcopy(cached_payload),
                "modified_time": modified_time,
            }
    return cached_payload


def store_acceptance_review_projects_cache(status_codes: list[str], payload: dict[str, Any]) -> None:
    cache_key = _acceptance_review_projects_cache_key(status_codes)
    ttl_seconds = acceptance_review_projects_cache_ttl_seconds()
    cached_payload = deepcopy(payload)
    cached_payload["cache_version"] = _ACCEPTANCE_REVIEW_PROJECTS_CACHE_VERSION
    if ttl_seconds > 0:
        with _ACCEPTANCE_REVIEW_PROJECTS_CACHE_LOCK:
            _ACCEPTANCE_REVIEW_PROJECTS_CACHE[cache_key] = {
                "expires_at": time.monotonic() + ttl_seconds,
                "payload": deepcopy(cached_payload),
            }
    write_api_result(
        api_name=f"acceptance_review_projects_cache_{cache_key.replace(',', '_')}",
        method="GET",
        path=f"/projectAccept/cache?statusCodes={urllib.parse.quote(cache_key)}",
        payload=None,
        scene="acceptance",
        result=cached_payload,
        error="",
    )


def _extract_project_list_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or {}
    data = result.get("data") or {}
    records = data.get("dataList")
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    return []


def _extract_task_order_list_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or {}
    data = result.get("data") or {}
    for key in ["records", "rows", "list", "items", "dataList"]:
        records = data.get(key)
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    return []


def infer_project_id(path: str, payload: dict[str, Any] | None = None, explicit_project_id: str | None = None) -> str:
    if explicit_project_id:
        return str(explicit_project_id).strip()

    if isinstance(payload, dict):
        for key in ["projectId", "project_id", "id"]:
            value = str(payload.get(key, "") or "").strip()
            if value:
                return value

    normalized_path = str(path or "").strip()
    if not normalized_path:
        return ""
    if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
        normalized_path = urllib.parse.urlparse(normalized_path).path

    for pattern in [
        r"/projectUploading/list/([^/?#]+)",
        r"/project/goal/get/([^/?#]+)",
        r"/value/info(?:NoTam)?/([^/?#]+)",
        r"/milestone/newList/([^/?#]+)",
        r"/budget/info/([^/?#]+)",
        r"/change/list/([^/?#]+)",
        r"/projectOrgFramework/list/([^/?#]+)",
    ]:
        match = re.search(pattern, normalized_path)
        if match:
            return match.group(1).strip()
    return ""


def load_cached_project_list(
    *,
    scene: str = "initiation",
    page_num: int,
    page_size: int,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    candidates: list[tuple[int, float, Path, dict[str, Any], list[dict[str, Any]]]] = []
    for search_dir in api_result_search_dirs(scene):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*_project_list.json"):
            if not path.is_file():
                continue
            try:
                payload = read_json(path)
                records = _extract_project_list_records(payload)
            except Exception:
                continue
            if not records:
                continue
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0
            rank = 0 if search_dir == scene_api_result_dir(normalize_scene(scene)) else 1
            candidates.append((rank, mtime, path, payload, records))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_payload = candidates[0][3]
    best_records = candidates[0][4]
    result_data = {
        "records": best_records,
        "total": len(best_records),
        "page_num": page_num,
        "page_size": page_size,
        "filters": filters or {},
        "source": "cache",
    }
    result_payload = {
        "code": 0,
        "message": "success",
        "data": result_data,
    }
    return result_payload


def load_cached_project_summary(project_id: str, scene: str = "initiation") -> dict[str, Any] | None:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return None

    for search_dir in api_result_search_dirs(scene):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*_project_list.json"):
            if not path.is_file():
                continue
            try:
                payload = read_json(path)
                records = _extract_project_list_records(payload)
            except Exception:
                continue
            for item in records:
                if str(item.get("id") or "").strip() == normalized_project_id:
                    return deepcopy(item)

    for search_dir in api_result_search_dirs("task_order"):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*_task_order_list.json"):
            if not path.is_file():
                continue
            try:
                payload = read_json(path)
                records = _extract_task_order_list_records(payload)
            except Exception:
                continue
            for item in records:
                if str(item.get("projectId") or "").strip() == normalized_project_id:
                    return deepcopy(item)
    return None


def load_cached_task_orders_by_project(project_id: str) -> list[dict[str, Any]]:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return []
    candidates: list[tuple[int, float, list[dict[str, Any]]]] = []
    for search_dir in api_result_search_dirs("task_order"):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*_task_order_list.json"):
            if not path.is_file():
                continue
            try:
                payload = read_json(path)
                records = _extract_task_order_list_records(payload)
            except Exception:
                continue
            matched = [item for item in records if str(item.get("projectId") or "").strip() == normalized_project_id]
            if not matched:
                continue
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0
            rank = 0 if search_dir == scene_api_result_dir("task_order") else 1
            candidates.append((rank, mtime, matched))

    if not candidates:
        return []

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return deepcopy(candidates[0][2])


def _build_snapshot_endpoint_from_cache_record(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("result")
    if isinstance(result, dict):
        return {
            "ok": result.get("code") == 0,
            "code": result.get("code"),
            "message": result.get("message"),
            "data": result.get("data"),
        }
    return {"ok": False, "code": -1, "message": str(record.get("error") or "Missing cached payload"), "data": None}


def load_cached_project_snapshot(project_id: str, scene: str = "initiation") -> dict[str, Any] | None:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return None
    endpoint_entries: dict[str, tuple[float, dict[str, Any]]] = {}
    for search_dir in api_result_search_dirs(scene):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*.json"):
            try:
                record = read_json(path)
            except Exception:
                continue
            if str(record.get("project_id") or "").strip() != normalized_project_id:
                continue
            api_name = str(record.get("api_name") or "").strip()
            if not api_name:
                continue
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0
            endpoint_payload = _build_snapshot_endpoint_from_cache_record(record)
            cached = endpoint_entries.get(api_name)
            if cached is None or mtime > cached[0]:
                endpoint_entries[api_name] = (mtime, endpoint_payload)

    if not endpoint_entries:
        return None

    return {
        "project_id": normalized_project_id,
        "endpoints": {name: payload for name, (_, payload) in endpoint_entries.items()},
    }
