from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config.paths import LEGACY_APPROVAL_RUNS_DIR, scene_approval_runs_dir
from app.core.config.scenes import SCENE_ACCEPTANCE, normalize_scene

LOGGER = logging.getLogger("project_approval.startup")

ACCEPTANCE_DETAIL_ENDPOINT_KEYS = [
    "acceptance_task_info",
    "acceptance_contract_info",
    "acceptance_stage_tasks",
    "acceptance_stage_contracts",
    "acceptance_count_data",
]


def _normalize_list(value: Any) -> list[Any]:
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


def parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def acceptance_snapshot_has_detail_endpoints(snapshot: dict[str, Any] | None) -> bool:
    endpoints = (snapshot or {}).get("endpoints") or {}
    if not isinstance(endpoints, dict):
        return False
    return any(key in endpoints for key in ACCEPTANCE_DETAIL_ENDPOINT_KEYS)


def acceptance_snapshot_has_accept_info(snapshot: dict[str, Any] | None) -> bool:
    endpoints = (snapshot or {}).get("endpoints") or {}
    if not isinstance(endpoints, dict):
        return False
    acceptance_info = (endpoints.get("acceptance_info_list") or {}).get("data")
    return bool(_normalize_list(acceptance_info))


def stale_acceptance_persisted_document(document: dict[str, Any] | None, snapshot: dict[str, Any] | None) -> bool:
    if not acceptance_snapshot_has_accept_info(snapshot):
        return False
    if acceptance_snapshot_has_detail_endpoints(snapshot):
        return False
    acceptance = (document or {}).get("acceptance") or {}
    if not isinstance(acceptance, dict):
        return True
    for key in ["task_list", "contract_list", "task_acceptance_list", "contract_acceptance_list", "deliverables"]:
        if _normalize_list(acceptance.get(key)):
            return False
    return True


def stale_acceptance_approval_payload(payload: dict[str, Any]) -> bool:
    if normalize_scene(payload.get("scene")) != SCENE_ACCEPTANCE:
        return False
    run_dir_text = str(payload.get("run_dir") or "").strip()
    if not run_dir_text:
        return False
    snapshot_path = Path(run_dir_text) / "project_snapshot.json"
    if not snapshot_path.exists():
        return False
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not acceptance_snapshot_has_accept_info(snapshot):
        return False
    return not acceptance_snapshot_has_detail_endpoints(snapshot)


def load_latest_remote_approval_result(
    project_id: str,
    category: str,
    scene: str = "initiation",
    *,
    default_project_category: str,
) -> dict[str, Any] | None:
    normalized_scene = normalize_scene(scene)
    run_dirs = [scene_approval_runs_dir(normalized_scene)]
    if normalized_scene == "initiation":
        run_dirs.append(LEGACY_APPROVAL_RUNS_DIR)
    if not any(path.exists() for path in run_dirs):
        return None

    latest_payload: dict[str, Any] | None = None
    latest_timestamp = float("-inf")
    for run_dir in run_dirs:
        if not run_dir.exists():
            continue
        for result_path in run_dir.glob("*/approval_result.json"):
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                LOGGER.warning("Skipping unreadable approval result: %s", result_path)
                continue

            if str(payload.get("project_id") or "") != project_id:
                continue
            if str(payload.get("category") or default_project_category) != category:
                continue
            if normalize_scene(payload.get("scene")) != normalized_scene:
                continue
            if stale_acceptance_approval_payload(payload):
                continue

            generated_at = parse_iso_datetime(payload.get("generated_at"))
            sort_timestamp = generated_at.timestamp() if generated_at else result_path.stat().st_mtime
            if sort_timestamp >= latest_timestamp:
                latest_timestamp = sort_timestamp
                latest_payload = payload

    return latest_payload


def load_latest_remote_approval_result_any_category(
    project_id: str,
    scene: str = "initiation",
) -> dict[str, Any] | None:
    normalized_scene = normalize_scene(scene)
    run_dirs = [scene_approval_runs_dir(normalized_scene)]
    if normalized_scene == "initiation":
        run_dirs.append(LEGACY_APPROVAL_RUNS_DIR)
    if not any(path.exists() for path in run_dirs):
        return None

    latest_payload: dict[str, Any] | None = None
    latest_timestamp = float("-inf")
    for run_dir in run_dirs:
        if not run_dir.exists():
            continue
        for result_path in run_dir.glob("*/approval_result.json"):
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                LOGGER.warning("Skipping unreadable approval result: %s", result_path)
                continue

            if str(payload.get("project_id") or "") != project_id:
                continue
            if normalize_scene(payload.get("scene")) != normalized_scene:
                continue
            if stale_acceptance_approval_payload(payload):
                continue

            generated_at = parse_iso_datetime(payload.get("generated_at"))
            sort_timestamp = generated_at.timestamp() if generated_at else result_path.stat().st_mtime
            if sort_timestamp >= latest_timestamp:
                latest_timestamp = sort_timestamp
                latest_payload = payload

    return latest_payload


def load_latest_remote_approval_result_map(
    category: str,
    scene: str = "initiation",
    *,
    default_project_category: str,
) -> dict[str, dict[str, Any]]:
    normalized_scene = normalize_scene(scene)
    run_dirs = [scene_approval_runs_dir(normalized_scene)]
    if normalized_scene == "initiation":
        run_dirs.append(LEGACY_APPROVAL_RUNS_DIR)
    if not any(path.exists() for path in run_dirs):
        return {}

    latest_items: dict[str, dict[str, Any]] = {}
    latest_timestamps: dict[str, float] = {}
    for run_dir in run_dirs:
        if not run_dir.exists():
            continue
        for result_path in run_dir.glob("*/approval_result.json"):
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                LOGGER.warning("Skipping unreadable approval result: %s", result_path)
                continue

            project_id = str(payload.get("project_id") or "").strip()
            if not project_id:
                continue
            if str(payload.get("category") or default_project_category) != category:
                continue
            if normalize_scene(payload.get("scene")) != normalized_scene:
                continue
            if stale_acceptance_approval_payload(payload):
                continue

            generated_at = parse_iso_datetime(payload.get("generated_at"))
            sort_timestamp = generated_at.timestamp() if generated_at else result_path.stat().st_mtime
            if sort_timestamp >= latest_timestamps.get(project_id, float("-inf")):
                latest_timestamps[project_id] = sort_timestamp
                latest_items[project_id] = payload

    return latest_items


def approval_result_to_review_record(payload: dict[str, Any]) -> dict[str, Any]:
    fallback_reason = str(payload.get("fallback_reason") or payload.get("fallbackReason") or payload.get("reason") or "")
    return {
        "decision": str(payload.get("decision") or ""),
        "summary": str(payload.get("summary") or ""),
        "risks": list(payload.get("risks") or []),
        "missingInformation": list(payload.get("missing_information") or []),
        "positiveEvidence": list(payload.get("positive_evidence") or []),
        "projectCommentary": str(payload.get("project_commentary") or ""),
        "baseline": payload.get("baseline") or None,
        "segments": list(payload.get("segments") or []),
        "runDir": str(payload.get("run_dir") or ""),
        "approvalGeneratedAt": str(payload.get("generated_at") or ""),
        "decisionSource": str(payload.get("decision_source") or payload.get("decisionSource") or ""),
        "reason": fallback_reason,
        "fallbackReason": fallback_reason,
    }


def merge_review_feedback_with_approvals(
    review_items: dict[str, dict[str, Any]],
    approval_items: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = {**review_items}
    approval_fields = [
        "decision",
        "summary",
        "risks",
        "missingInformation",
        "positiveEvidence",
        "projectCommentary",
        "baseline",
        "segments",
        "runDir",
        "approvalGeneratedAt",
        "decisionSource",
        "reason",
        "fallbackReason",
    ]

    def _parse_feedback_approval_time(record: dict[str, Any]) -> float:
        value = record.get("approvalGeneratedAt") or record.get("generatedAt")
        parsed = parse_iso_datetime(value)
        return parsed.timestamp() if parsed else float("-inf")

    for project_id, approval_payload in approval_items.items():
        approval_record = approval_result_to_review_record(approval_payload)
        existing = dict(merged.get(project_id) or {})
        existing_approval_ts = _parse_feedback_approval_time(existing)
        incoming_approval_ts = _parse_feedback_approval_time(approval_record)
        keep_existing_approval = existing_approval_ts >= incoming_approval_ts

        merged_item = {**existing}
        for field in approval_fields:
            if keep_existing_approval:
                merged_item[field] = existing.get(field) if field in existing else approval_record.get(field)
            else:
                merged_item[field] = approval_record.get(field)
        merged[project_id] = merged_item
    return merged
