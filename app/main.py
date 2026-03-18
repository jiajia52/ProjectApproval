"""FastAPI service aligned with the auto_approval-style project layout."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
from concurrent import futures
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app.approvals.approval_engine import (
    evaluate_approval,
    load_generated_project_bundle,
    load_or_create_sample_document,
    normalize_generated_bundle,
)
from app.approvals.iwork_client import (
    IworkProjectClient,
    RemoteAPIError,
    load_cached_project_snapshot,
    load_cached_project_summary,
    load_integration_config,
    matches_project_filters,
    save_integration_config,
)
from app.approvals.llm_approval_service import run_llm_approval
from app.approvals.project_document_store import load_project_document, persist_project_document
from app.approvals.review_feedback_store import load_latest_review_feedback_map, persist_review_feedback
from app.approvals.remote_project_mapper import map_snapshot_to_document
from app.approvals.category_aliases import CATEGORY_NAME_ALIASES, canonical_category_name
from app.core.startup_checks import run_startup_checks
from app.core.paths import (
    APPROVAL_RUNS_DIR,
    CONFIG_PATH,
    FRONTEND_DIR,
    GENERATED_DIR,
    LEGACY_FRONTEND_DIR,
    PROJECT_ROOT,
    RULES_BUNDLE_PATH,
    SKILL_MANIFEST_PATH,
    SCRIPTS_DIR,
    find_rule_matrix_path,
)
from app.skills.manager import get_skill_manager

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_project_approval_bundle import build_project_bundle, load_or_create_config, resolve_rule_matrix_path  # noqa: E402
from extract_review_rules import parse_rule_bundle  # noqa: E402
from generate_approval_item_skills import generate_approval_item_skills  # noqa: E402

LOGGER = logging.getLogger("project_approval.startup")
DEFAULT_PROJECT_CATEGORY = "工作台开发及实施"
ADMIN_SESSION_COOKIE = "project_approval_admin_session"
ADMIN_SESSION_MAX_AGE = 8 * 60 * 60
_ARCH_REVIEW_CACHE_LOCK = threading.Lock()
_ARCH_REVIEW_CACHE: dict[str, dict[str, Any]] = {}


def get_management_credentials() -> tuple[str, str]:
    username = os.getenv("PROJECT_APPROVAL_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("PROJECT_APPROVAL_ADMIN_PASSWORD", "admin123")
    return username, password


def ensure_admin_sessions(app_instance: FastAPI) -> dict[str, dict[str, Any]]:
    sessions = getattr(app_instance.state, "admin_sessions", None)
    if not isinstance(sessions, dict):
        sessions = {}
        app_instance.state.admin_sessions = sessions
    return sessions


def get_admin_session(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "").strip()
    if not token:
        return None
    return ensure_admin_sessions(request.app).get(token)


def require_management_auth(request: Request) -> dict[str, Any]:
    session = get_admin_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="需要先登录管理界面。")
    return session


def list_outputs() -> list[dict[str, str]]:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, str]] = []
    for path in sorted(GENERATED_DIR.glob("*")):
        if path.is_file():
            outputs.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                }
            )
    return outputs


def parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def architecture_review_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_ARCH_REVIEW_CACHE_TTL", "45") or "45").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 45
    return max(0, min(ttl, 300))


def _load_cached_architecture_reviews(project_id: str) -> list[dict[str, Any]] | None:
    ttl_seconds = architecture_review_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return None
    cache_key = str(project_id or "").strip()
    if not cache_key:
        return None
    now = time.monotonic()
    with _ARCH_REVIEW_CACHE_LOCK:
        record = _ARCH_REVIEW_CACHE.get(cache_key)
        if not record:
            return None
        if float(record.get("expires_at") or 0) <= now:
            _ARCH_REVIEW_CACHE.pop(cache_key, None)
            return None
        groups = record.get("groups")
        if isinstance(groups, list):
            return json.loads(json.dumps(groups, ensure_ascii=False))
    return None


def _store_cached_architecture_reviews(project_id: str, groups: list[dict[str, Any]]) -> None:
    ttl_seconds = architecture_review_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return
    cache_key = str(project_id or "").strip()
    if not cache_key:
        return
    with _ARCH_REVIEW_CACHE_LOCK:
        _ARCH_REVIEW_CACHE[cache_key] = {
            "expires_at": time.monotonic() + ttl_seconds,
            "groups": json.loads(json.dumps(groups, ensure_ascii=False)),
        }


def normalize_category_key(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(character for character in text if character.isalnum())


def known_category_lookup() -> dict[str, str]:
    _, rules_bundle = ensure_runtime_artifacts(force=False)
    lookup = {
        normalize_category_key(item.get("name")): str(item.get("name"))
        for item in rules_bundle.get("categories", [])
        if str(item.get("name") or "").strip()
    }
    for alias, target in CATEGORY_NAME_ALIASES.items():
        canonical_key = normalize_category_key(target)
        if canonical_key in lookup:
            lookup[normalize_category_key(alias)] = lookup[canonical_key]
    return lookup


def resolve_project_category_name(
    requested_category: str | None = None,
    summary: dict[str, Any] | None = None,
    document: dict[str, Any] | None = None,
) -> str:
    category_lookup = known_category_lookup()
    if not category_lookup:
        fallback = canonical_category_name(requested_category or DEFAULT_PROJECT_CATEGORY)
        return str(fallback or DEFAULT_PROJECT_CATEGORY).strip() or DEFAULT_PROJECT_CATEGORY

    summary_candidates: list[Any] = []
    if isinstance(summary, dict):
        summary_candidates.extend(
            [
                summary.get("business_subcategory_name"),
                summary.get("businessSubcategoryName"),
                summary.get("projectClassifyName"),
                summary.get("project_category_name"),
                summary.get("projectCategoryName"),
                summary.get("project_type_name"),
                summary.get("projectTypeName"),
            ]
        )
    if isinstance(document, dict):
        document_summary = document.get("project_summary")
        if isinstance(document_summary, dict):
            summary_candidates.extend(
                [
                    document_summary.get("business_subcategory_name"),
                    document_summary.get("project_category_name"),
                    document_summary.get("project_type_name"),
                ]
            )

    for candidate in summary_candidates:
        normalized = normalize_category_key(canonical_category_name(candidate))
        if normalized and normalized in category_lookup:
            return category_lookup[normalized]

    requested_normalized = normalize_category_key(canonical_category_name(requested_category))
    if requested_normalized and requested_normalized in category_lookup:
        return category_lookup[requested_normalized]
    return category_lookup.get(normalize_category_key(DEFAULT_PROJECT_CATEGORY), DEFAULT_PROJECT_CATEGORY)


def load_latest_remote_approval_result(project_id: str, category: str) -> dict[str, Any] | None:
    if not APPROVAL_RUNS_DIR.exists():
        return None

    latest_payload: dict[str, Any] | None = None
    latest_timestamp = float("-inf")
    for result_path in APPROVAL_RUNS_DIR.glob("*/approval_result.json"):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Skipping unreadable approval result: %s", result_path)
            continue

        if str(payload.get("project_id") or "") != project_id:
            continue
        if str(payload.get("category") or DEFAULT_PROJECT_CATEGORY) != category:
            continue

        generated_at = parse_iso_datetime(payload.get("generated_at"))
        sort_timestamp = generated_at.timestamp() if generated_at else result_path.stat().st_mtime
        if sort_timestamp >= latest_timestamp:
            latest_timestamp = sort_timestamp
            latest_payload = payload

    return latest_payload


def load_latest_remote_approval_result_map(category: str) -> dict[str, dict[str, Any]]:
    if not APPROVAL_RUNS_DIR.exists():
        return {}

    latest_items: dict[str, dict[str, Any]] = {}
    latest_timestamps: dict[str, float] = {}
    for result_path in APPROVAL_RUNS_DIR.glob("*/approval_result.json"):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Skipping unreadable approval result: %s", result_path)
            continue

        project_id = str(payload.get("project_id") or "").strip()
        if not project_id:
            continue
        if str(payload.get("category") or DEFAULT_PROJECT_CATEGORY) != category:
            continue

        generated_at = parse_iso_datetime(payload.get("generated_at"))
        sort_timestamp = generated_at.timestamp() if generated_at else result_path.stat().st_mtime
        if sort_timestamp >= latest_timestamps.get(project_id, float("-inf")):
            latest_timestamps[project_id] = sort_timestamp
            latest_items[project_id] = payload

    return latest_items


def approval_result_to_review_record(payload: dict[str, Any]) -> dict[str, Any]:
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
    }


def merge_review_feedback_with_approvals(
    review_items: dict[str, dict[str, Any]],
    approval_items: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = {**review_items}
    for project_id, approval_payload in approval_items.items():
        approval_record = approval_result_to_review_record(approval_payload)
        existing = dict(merged.get(project_id) or {})
        merged[project_id] = {
            **approval_record,
            **existing,
            "decision": existing.get("decision") or approval_record["decision"],
            "summary": existing.get("summary") or approval_record["summary"],
            "risks": existing.get("risks") or approval_record["risks"],
            "missingInformation": existing.get("missingInformation") or approval_record["missingInformation"],
            "positiveEvidence": existing.get("positiveEvidence") or approval_record["positiveEvidence"],
            "projectCommentary": existing.get("projectCommentary") or approval_record["projectCommentary"],
            "baseline": existing.get("baseline") or approval_record["baseline"],
            "segments": existing.get("segments") or approval_record["segments"],
            "runDir": existing.get("runDir") or approval_record["runDir"],
            "approvalGeneratedAt": existing.get("approvalGeneratedAt") or approval_record["approvalGeneratedAt"],
        }
    return merged


def to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RemoteAPIError):
        return HTTPException(status_code=502, detail=f"远程接口返回错误[{exc.code}]: {exc.message}")
    return HTTPException(status_code=502, detail=str(exc))


def should_rebuild_bundle(rule_matrix_path: Path) -> bool:
    return not RULES_BUNDLE_PATH.exists() or RULES_BUNDLE_PATH.stat().st_mtime < rule_matrix_path.stat().st_mtime


def should_regenerate_skills(rule_matrix_path: Path) -> bool:
    if not SKILL_MANIFEST_PATH.exists():
        return True
    if SKILL_MANIFEST_PATH.stat().st_mtime < rule_matrix_path.stat().st_mtime:
        return True
    try:
        payload = json.loads(SKILL_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return True
    skills_dir_prefix = str(PROJECT_ROOT / "skills")
    for skill in payload.get("skills", []):
        directory = str(skill.get("directory", ""))
        if not directory.startswith(skills_dir_prefix):
            return True
        if not Path(directory).exists():
            return True
    return False


def ensure_runtime_artifacts(*, force: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    rule_matrix_path = find_rule_matrix_path()
    bootstrap_rules = parse_rule_bundle(rule_matrix_path)
    config = load_or_create_config(CONFIG_PATH, PROJECT_ROOT, bootstrap_rules)
    rule_source_path = resolve_rule_matrix_path(PROJECT_ROOT, config)
    rules_bundle = parse_rule_bundle(rule_source_path)

    if force or should_rebuild_bundle(rule_source_path):
        build_project_bundle(root=PROJECT_ROOT, config_path=CONFIG_PATH)
        rules_bundle = parse_rule_bundle(rule_source_path)

    if force or should_regenerate_skills(rule_source_path):
        enabled_skill_groups = set(config.get("generation", {}).get("enabled_skill_groups", []))
        generate_approval_item_skills(rules_bundle, enabled_review_points=enabled_skill_groups or None)

    get_skill_manager().initialize()
    return config, rules_bundle


def refresh_startup_checks(app_instance: FastAPI, *, rules_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = run_startup_checks(rules_bundle=rules_bundle)
    app_instance.state.startup_checks = payload
    for item in payload["checks"]:
        log_fn = LOGGER.info if item["status"] == "ok" else LOGGER.warning
        log_fn("startup-check %s [%s] %s", item["name"], item["status"], item["message"])
    return payload


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


def build_project_document(
    *,
    client: IworkProjectClient,
    project_id: str,
    category: str,
    refresh: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    cached_record = None if refresh else load_project_document(project_id, category)
    if cached_record:
        cached_document = dict(cached_record.get("document") or {})
        cached_document["document_source"] = str(cached_record.get("source") or "persisted")
        cached_document["document_saved_at"] = cached_record.get("saved_at")
        cached_snapshot = cached_record.get("snapshot") or cached_document.get("remote_snapshot") or {"project_id": project_id, "endpoints": {}}
        return cached_document, cached_snapshot, "persisted"

    remote_snapshot = client.fetch_project_snapshot(project_id, force_refresh=refresh)
    api_cache_snapshot = load_cached_project_snapshot(project_id)
    snapshot = merge_project_snapshots(remote_snapshot, api_cache_snapshot)
    source = "remote" if snapshot_has_usable_data(remote_snapshot) else "api_result_cache"
    if not snapshot_has_usable_data(snapshot):
        source = "remote"

    project_summary = load_cached_project_summary(project_id) or {"id": project_id}
    document = map_snapshot_to_document(snapshot, project_summary, category)
    architecture_review_groups = None if refresh else _load_cached_architecture_reviews(project_id)
    if architecture_review_groups is None:
        architecture_review_groups = collect_architecture_review_groups(
            client=client,
            project_id=project_id,
            snapshot=snapshot,
        )
        _store_cached_architecture_reviews(project_id, architecture_review_groups)
    document["architecture_reviews"] = review_groups_to_document_fields(architecture_review_groups)
    document["architecture_review_details"] = architecture_review_groups
    document["document_source"] = source
    document["document_saved_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    persist_project_document(
        project_id=project_id,
        category=category,
        document=document,
        source=source,
        snapshot=snapshot,
        project_summary=project_summary,
    )
    return document, snapshot, source


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


def _pick_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _normalize_review_conclusion(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in {"1", "通过", "pass", "PASS"}:
        return "通过"
    if normalized in {"0", "不通过", "fail", "FAIL"}:
        return "不通过"
    return normalized


def _sum_unique_ints(rows: list[dict[str, Any]], key: str, identity_key: str) -> int:
    values: dict[str, int] = {}
    for row in rows:
        identity = str(row.get(identity_key) or row.get("id") or "").strip()
        if not identity:
            identity = f"row-{len(values)}"
        try:
            values[identity] = max(values.get(identity, 0), int(row.get(key) or 0))
        except Exception:
            values[identity] = values.get(identity, 0)
    return sum(values.values())


def _iter_tree_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    stack = list(nodes)
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        items.append(current)
        children = current.get("children")
        if isinstance(children, list):
            stack.extend(children)
    return items


def _extract_product_context(snapshot: dict[str, Any]) -> dict[str, str]:
    dev_scope = ((snapshot.get("endpoints") or {}).get("project_scope_dev") or {}).get("data") or {}
    flow_rows = normalize_list(dev_scope.get("projectRangeFlowEntities"))
    for row in flow_rows:
        if not isinstance(row, dict):
            continue
        product_id = str(row.get("productId") or "").strip()
        if product_id:
            return {"product_id": product_id, "product_name": str(row.get("productName") or "").strip()}
    return {"product_id": "", "product_name": ""}


def _build_business_review_summary(snapshot: dict[str, Any]) -> dict[str, int]:
    dev_scope = ((snapshot.get("endpoints") or {}).get("project_scope_dev") or {}).get("data") or {}
    flow_rows = [item for item in normalize_list(dev_scope.get("projectRangeFlowEntities")) if isinstance(item, dict)]
    unique_product_ids = {str(item.get("productId") or "").strip() for item in flow_rows if str(item.get("productId") or "").strip()}
    unique_process_ids = {
        str(item.get("processVersionId") or item.get("processId") or item.get("id") or "").strip()
        for item in flow_rows
        if str(item.get("processVersionId") or item.get("processId") or item.get("id") or "").strip()
    }
    tree_nodes = _iter_tree_nodes(normalize_list(dev_scope.get("projectRangeEaMapTreeEntities")))
    business_object_count = _sum_unique_ints(flow_rows, "busObjNum", "processVersionId")
    if not business_object_count:
        business_object_count = len(
            [
                node
                for node in tree_nodes
                if "对象" in str(node.get("type") or "") or "对象" in str(node.get("typeName") or "") or "对象" in str(node.get("name") or "")
            ]
        )
    return {
        "product_count": len(unique_product_ids),
        "business_process_count": len(unique_process_ids),
        "business_unit_count": _sum_unique_ints(flow_rows, "busNum", "processVersionId"),
        "business_object_count": business_object_count,
    }


def _normalize_review_items(items: Any) -> list[dict[str, Any]]:
    rows = normalize_list(items)
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            normalized.append(
                {
                    "id": f"review-{index}",
                    "index": index,
                    "dimension": "",
                    "checkpoint": str(row),
                    "value_model": "",
                    "reviewer": "",
                    "conclusion": "",
                    "description": "",
                }
            )
            continue
        normalized.append(
            {
                "id": str(row.get("id") or f"review-{index}"),
                "index": index,
                "dimension": _pick_text(row, "dimension", "dimensionName", "typeName", "type"),
                "checkpoint": _pick_text(row, "checkpoint", "checkPoint", "checkpointName", "name", "title"),
                "value_model": _pick_text(
                    row,
                    "valuePropositionModel",
                    "reviewModel",
                    "reviewStandard",
                    "reviewContent",
                    "content",
                    "description",
                ),
                "reviewer": _pick_text(
                    row,
                    "reviewer",
                    "initialReviewer",
                    "preliminaryInterrogator",
                    "creator",
                    "createUser",
                    "auditUser",
                ),
                "conclusion": _normalize_review_conclusion(
                    _pick_text(
                        row,
                        "reviewConclusion",
                        "preliminaryConclusion",
                        "conclusion",
                        "result",
                        "statusName",
                        "status",
                    )
                ),
                "description": _pick_text(row, "reviewDescription", "remark", "opinion", "description"),
            }
        )
    return normalized


def _is_information_architecture_item(item: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(item.get("dimension") or ""),
            str(item.get("checkpoint") or ""),
            str(item.get("value_model") or ""),
        ]
    )
    return "信息架构" in haystack or "概念模型" in haystack or "业务对象" in haystack


def _is_information_architecture_item(item: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(item.get("dimension") or ""),
            str(item.get("checkpoint") or ""),
            str(item.get("value_model") or ""),
        ]
    )
    return "信息架构" in haystack or "概念模型" in haystack or "业务对象" in haystack


def _fetch_data_review(client: IworkProjectClient, project_id: str) -> dict[str, Any]:
    result = client.request_json(
        "GET",
        f"/initiationTask/result?projectId={project_id}",
        strict=False,
        api_name="architecture_review_data",
        project_id=project_id,
    )
    data = result.get("data")
    items = _normalize_review_items(data)
    return {
        "key": "data",
        "title": "数据架构评审状态",
        "link_label": "前往信息架构中心查看",
        "ok": result.get("code") == 0,
        "message": str(result.get("message") or ""),
        "summary": {
            "flow_dimension_count": len({item.get("dimension") for item in items if item.get("dimension")}),
            "check_point_count": len(items),
        },
        "items": items,
    }


def _fetch_technology_review_fallback(client: IworkProjectClient, project_id: str) -> dict[str, Any]:
    result = client.request_json(
        "POST",
        "/projectMicosInfo/getList",
        payload={"projectId": project_id, "dataType": 1},
        strict=False,
        api_name="architecture_review_technology_fallback",
        project_id=project_id,
    )
    items: list[dict[str, Any]] = []
    for index, row in enumerate(normalize_list(result.get("data")), start=1):
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "id": str(row.get("id") or f"tech-fallback-{index}"),
                "index": index,
                "dimension": "技术架构",
                "checkpoint": _pick_text(row, "subName", "systemName", "name"),
                "value_model": f"系统编码: {_pick_text(row, 'systemCode', 'subCode')}；负责人: {_pick_text(row, 'subLeader', 'owner', 'leader')}",
                "reviewer": "",
                "conclusion": "通过",
                "description": _pick_text(row, "subLevelStandard", "subType", "systemName"),
            }
        )
    return {
        "key": "technology",
        "title": "技术架构评审状态",
        "link_label": "前往云原生查看",
        "ok": result.get("code") == 0 and len(items) > 0,
        "message": "技术架构评审接口未返回明细，已回退使用系统范围(dataType=1)内容作为技术架构材料。"
        if items
        else str(result.get("message") or ""),
        "summary": {
            "app_count": 0,
            "service_count": len(items),
            "type": "fallback",
        },
        "items": items,
    }


def _fetch_technology_review_fallback(client: IworkProjectClient, project_id: str) -> dict[str, Any]:
    result = client.request_json(
        "POST",
        "/projectMicosInfo/getList",
        payload={"projectId": project_id, "dataType": 1},
        strict=False,
        api_name="architecture_review_technology_fallback",
        project_id=project_id,
    )
    items: list[dict[str, Any]] = []
    for index, row in enumerate(normalize_list(result.get("data")), start=1):
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "id": str(row.get("id") or f"tech-fallback-{index}"),
                "index": index,
                "dimension": "技术架构",
                "checkpoint": _pick_text(row, "subName", "systemName", "name"),
                "value_model": f"系统编码: {_pick_text(row, 'systemCode', 'subCode')}；负责人: {_pick_text(row, 'subLeader', 'owner', 'leader')}",
                "reviewer": "",
                "conclusion": "通过",
                "description": _pick_text(row, "subLevelStandard", "subType", "systemName"),
            }
        )
    return {
        "key": "technology",
        "title": "技术架构评审状态",
        "link_label": "前往云原生查看",
        "ok": result.get("code") == 0 and len(items) > 0,
        "message": "技术架构评审接口未返回明细，已回退使用系统范围(dataType=1)内容作为技术架构材料。"
        if items
        else str(result.get("message") or ""),
        "summary": {
            "app_count": 0,
            "service_count": len(items),
            "type": "fallback",
        },
        "items": items,
    }


def _fetch_technology_review(client: IworkProjectClient, project_id: str) -> dict[str, Any]:
    type_values = [1, 2, 3, 4, 5, 6]
    candidates: list[dict[str, Any]] = []

    with futures.ThreadPoolExecutor(max_workers=min(6, len(type_values))) as executor:
        future_map = {
            executor.submit(
                client.request_json,
                "POST",
                "/third/techCheckList",
                payload={"projectId": project_id, "type": type_value},
                strict=False,
                api_name=f"architecture_review_technology_type_{type_value}",
                project_id=project_id,
            ): type_value
            for type_value in type_values
        }
        for future in futures.as_completed(future_map):
            type_value = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"code": -1, "message": str(exc), "data": {}}
            data = result.get("data") or {}
            items = _normalize_review_items(data)
            candidates.append(
                {
                    "type": type_value,
                    "result": result,
                    "items": items,
                    "data": data,
                }
            )

    if not candidates:
        fallback = _fetch_technology_review_fallback(client, project_id)
        if fallback.get("ok"):
            return fallback
        raise RuntimeError("Technology architecture review returned no candidates.")

    candidates.sort(key=lambda item: int(item.get("type") or 0))
    chosen = next(
        (
            item
            for item in candidates
            if item["result"].get("code") == 200
            and (item["items"] or int((item["data"] or {}).get("appCount") or 0) or int((item["data"] or {}).get("serviceCount") or 0))
        ),
        candidates[0],
    )
    chosen_data = chosen.get("data") or {}
    result = chosen["result"]
    if not chosen["items"]:
        fallback = _fetch_technology_review_fallback(client, project_id)
        if fallback.get("ok"):
            return fallback
    return {
        "key": "technology",
        "title": "技术架构评审状态",
        "link_label": "前往云原生查看",
        "ok": result.get("code") == 200,
        "message": str(result.get("message") or ""),
        "summary": {
            "app_count": int(chosen_data.get("appCount") or 0),
            "service_count": int(chosen_data.get("serviceCount") or 0),
            "type": chosen["type"],
        },
        "items": chosen["items"],
    }


def _fetch_security_review(client: IworkProjectClient, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    endpoints = snapshot.get("endpoints") or {}
    base_info = (endpoints.get("project_base_info") or {}).get("data") or {}
    dev_scope = (endpoints.get("project_scope_dev") or {}).get("data") or {}
    related_systems = [item for item in normalize_list(dev_scope.get("projectRelatedSystemEntities")) if isinstance(item, dict)]
    system_code = str((related_systems[0].get("code") if related_systems else "") or "").strip()
    payload = {
        "projectId": project_id,
        "projectCode": str(base_info.get("serialNo") or "").strip(),
        "systemCode": system_code,
        "type": 1,
    }
    result = client.request_json(
        "POST",
        "/third/securityCheckList",
        payload=payload,
        strict=False,
        api_name="architecture_review_security",
        project_id=project_id,
    )
    data = result.get("data") or {}
    items = _normalize_review_items(data)
    return {
        "key": "security",
        "title": "安全架构评审状态",
        "link_label": "前往应用开发安全平台查看",
        "ok": result.get("code") == 200,
        "message": str(result.get("message") or ""),
        "summary": {
            "app_count": int(data.get("appCount") or 0),
            "service_count": int(data.get("serviceCount") or 0),
            "safety_level": str(data.get("safetyLevel") or ""),
        },
        "items": items,
    }


def _build_review_error_group(key: str, title: str, link_label: str, message: str) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "link_label": link_label,
        "ok": False,
        "message": message,
        "summary": {},
        "items": [],
    }


def collect_architecture_review_groups(
    *,
    client: IworkProjectClient,
    project_id: str,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    product_context = _extract_product_context(snapshot)
    business_items: list[dict[str, Any]] = []
    business_ok = False
    business_message = ""
    if product_context["product_id"]:
        try:
            business_result = client.request_json(
                "GET",
                f"/projectBaseInfo/getProductCheckStatus/{product_context['product_id']}",
                strict=False,
                api_name="architecture_review_business",
                project_id=project_id,
            )
            business_items = _normalize_review_items(business_result.get("data"))
            business_ok = business_result.get("code") == 0
            business_message = str(business_result.get("message") or "")
        except Exception as exc:
            business_message = str(exc)
    else:
        business_message = "未在项目范围-开发接口中找到产品ID，无法调用业务架构评审接口。"

    info_architecture_items = [item for item in business_items if _is_information_architecture_item(item)]
    business_items = [item for item in business_items if not _is_information_architecture_item(item)]

    groups = [
        {
            "key": "business",
            "title": "业务架构评审状态",
            "link_label": "前往EAMAP查看",
            "ok": business_ok and len(business_items) > 0,
            "message": business_message,
            "summary": _build_business_review_summary(snapshot),
            "items": business_items,
            "context": product_context,
        }
    ]

    async_groups: dict[str, dict[str, Any]] = {}
    async_errors: dict[str, str] = {}
    with futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(_fetch_data_review, client, project_id): "data",
            executor.submit(_fetch_technology_review, client, project_id): "technology",
            executor.submit(_fetch_security_review, client, project_id, snapshot): "security",
        }
        for future in futures.as_completed(future_map):
            group_key = future_map[future]
            try:
                async_groups[group_key] = future.result()
            except Exception as exc:
                async_errors[group_key] = str(exc)

    data_group = async_groups.get("data")
    if data_group is None:
        data_group = _build_review_error_group(
            "data",
            "Data Architecture Review",
            "Open Data Architecture Center",
            async_errors.get("data", "Unknown error"),
        )
    merged_items = info_architecture_items + list(data_group.get("items") or [])
    data_group["items"] = merged_items
    data_group["ok"] = bool(data_group.get("ok") or merged_items)
    data_group["summary"] = {
        "flow_dimension_count": len({item.get("dimension") for item in merged_items if item.get("dimension")}),
        "check_point_count": len(merged_items),
    }
    if info_architecture_items:
        base_message = str(data_group.get("message") or "").strip()
        data_group["message"] = f"{base_message} Merged information-architecture items from business review.".strip()
    groups.append(data_group)

    technology_group = async_groups.get("technology")
    if technology_group is None:
        technology_group = _build_review_error_group(
            "technology",
            "Technology Architecture Review",
            "Open Cloud Native Portal",
            async_errors.get("technology", "Unknown error"),
        )
    groups.append(technology_group)

    security_group = async_groups.get("security")
    if security_group is None:
        security_group = _build_review_error_group(
            "security",
            "Security Architecture Review",
            "Open Security Portal",
            async_errors.get("security", "Unknown error"),
        )
    groups.append(security_group)

    return groups

    try:
        data_group = _fetch_data_review(client, project_id)
        merged_items = info_architecture_items + list(data_group.get("items") or [])
        data_group["items"] = merged_items
        data_group["ok"] = bool(data_group.get("ok") or merged_items)
        data_group["summary"] = {
            "flow_dimension_count": len({item.get("dimension") for item in merged_items if item.get("dimension")}),
            "check_point_count": len(merged_items),
        }
        if info_architecture_items:
            base_message = str(data_group.get("message") or "").strip()
            data_group["message"] = f"{base_message} 已合并业务架构中的信息架构内容。".strip()
        groups.append(data_group)
    except Exception as exc:
        data_group = _build_review_error_group("data", "数据架构评审状态", "前往信息架构中心查看", str(exc))
        data_group["items"] = info_architecture_items
        data_group["ok"] = len(info_architecture_items) > 0
        data_group["summary"] = {
            "flow_dimension_count": len({item.get("dimension") for item in info_architecture_items if item.get("dimension")}),
            "check_point_count": len(info_architecture_items),
        }
        groups.append(data_group)

    try:
        groups.append(_fetch_technology_review(client, project_id))
    except Exception as exc:
        groups.append(_build_review_error_group("technology", "技术架构评审状态", "前往云原生查看", str(exc)))

    try:
        groups.append(_fetch_security_review(client, project_id, snapshot))
    except Exception as exc:
        groups.append(_build_review_error_group("security", "安全架构评审状态", "前往应用开发安全平台查看", str(exc)))

    return groups


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


def build_architecture_review_payload(
    *,
    client: IworkProjectClient,
    project_id: str,
    category: str,
    refresh: bool = False,
) -> dict[str, Any]:
    document, snapshot, source = build_project_document(
        client=client,
        project_id=project_id,
        category=category,
        refresh=refresh,
    )
    cached_groups = document.get("architecture_review_details")
    if not refresh and isinstance(cached_groups, list) and cached_groups:
        groups = cached_groups
    else:
        groups = None if refresh else _load_cached_architecture_reviews(project_id)
        if groups is None:
            groups = collect_architecture_review_groups(
                client=client,
                project_id=project_id,
                snapshot=snapshot,
            )
            _store_cached_architecture_reviews(project_id, groups)
    return {
        "project_id": project_id,
        "project_name": document.get("project_name") or project_id,
        "document_source": source,
        "groups": groups,
    }


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    ensure_admin_sessions(app_instance)
    _, rules_bundle = ensure_runtime_artifacts(force=False)
    checks = refresh_startup_checks(app_instance, rules_bundle=rules_bundle)
    if checks["overall_status"] == "error":
        raise RuntimeError("Critical startup checks failed. See runtime/startup_checks.json for details.")
    yield


app = FastAPI(title="Project Approval API", version="0.4.0", lifespan=lifespan)


def active_frontend_dir() -> Path:
    if FRONTEND_DIR.exists():
        return FRONTEND_DIR
    return LEGACY_FRONTEND_DIR


def using_legacy_frontend() -> bool:
    return active_frontend_dir() == LEGACY_FRONTEND_DIR


def frontend_index_file() -> Path:
    frontend_dir = active_frontend_dir()
    if frontend_dir == LEGACY_FRONTEND_DIR:
        return frontend_dir / "approval.html"
    return frontend_dir / "index.html"


def resolve_frontend_file(full_path: str) -> Path | None:
    frontend_dir = active_frontend_dir().resolve()
    candidate = (frontend_dir / full_path).resolve()
    if frontend_dir not in candidate.parents and candidate != frontend_dir:
        return None
    if candidate.is_file():
        return candidate
    return None


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/approval")


@app.get("/ui")
@app.get("/ui/")
def ui_root() -> FileResponse:
    return FileResponse(frontend_index_file())


@app.get("/ui/index.html", include_in_schema=False)
def ui_legacy_index() -> RedirectResponse:
    return RedirectResponse(url="/ui/approval")


@app.get("/ui/approval", include_in_schema=False)
def ui_approval() -> FileResponse:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "approval.html")
    return FileResponse(frontend_index_file())


@app.get("/ui/approval.html", include_in_schema=False)
def ui_legacy_approval() -> Response:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "approval.html")
    return RedirectResponse(url="/ui/approval")


@app.get("/ui/workbench.html", include_in_schema=False)
def ui_legacy_workbench(projectId: str | None = None) -> Response:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "workbench.html")
    query = f"?projectId={projectId}" if projectId else ""
    return RedirectResponse(url=f"/ui/workbench{query}")


@app.get("/ui/workbench", include_in_schema=False)
def ui_workbench() -> FileResponse:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "workbench.html")
    return FileResponse(frontend_index_file())


@app.get("/ui/skills.html", include_in_schema=False)
def ui_legacy_skills() -> Response:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "skills.html")
    return RedirectResponse(url="/ui/skills")


@app.get("/ui/rules.html", include_in_schema=False)
def ui_legacy_rules() -> Response:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "rules.html")
    return RedirectResponse(url="/ui/skills")


@app.get("/ui/project-viewer.html", include_in_schema=False)
def ui_legacy_project_viewer(projectId: str, category: str | None = None) -> Response:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "project-viewer.html")
    query = f"?category={category}" if category else ""
    return RedirectResponse(url=f"/ui/project/{projectId}{query}")


@app.get("/ui/project/{project_id}", include_in_schema=False)
def ui_project(project_id: str, category: str | None = None) -> Response:
    if using_legacy_frontend():
        query = f"&category={category}" if category else ""
        return RedirectResponse(url=f"/ui/project-viewer.html?projectId={project_id}{query}")
    return FileResponse(frontend_index_file())


@app.get("/ui/skills", include_in_schema=False)
def ui_skills() -> FileResponse:
    if using_legacy_frontend():
        return FileResponse(LEGACY_FRONTEND_DIR / "skills.html")
    return FileResponse(frontend_index_file())


@app.get("/ui/{full_path:path}", include_in_schema=False)
def ui_files(full_path: str) -> FileResponse:
    file_path = resolve_frontend_file(full_path)
    if file_path is not None:
        return FileResponse(file_path)
    return FileResponse(frontend_index_file())


@app.get("/api/admin/session")
def api_admin_session(request: Request) -> dict[str, Any]:
    session = get_admin_session(request)
    if session is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "username": session.get("username") or get_management_credentials()[0],
    }


@app.post("/api/admin/login")
def api_admin_login(payload: dict[str, Any]) -> JSONResponse:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    expected_username, expected_password = get_management_credentials()
    if not (
        hmac.compare_digest(username, expected_username)
        and hmac.compare_digest(password, expected_password)
    ):
        raise HTTPException(status_code=401, detail="账号或密码错误。")

    session_token = secrets.token_urlsafe(32)
    ensure_admin_sessions(app)[session_token] = {
        "username": expected_username,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    response = JSONResponse({"authenticated": True, "username": expected_username})
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=session_token,
        max_age=ADMIN_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/api/admin/logout")
def api_admin_logout(request: Request) -> JSONResponse:
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "").strip()
    if token:
        ensure_admin_sessions(request.app).pop(token, None)
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(ADMIN_SESSION_COOKIE, samesite="lax")
    return response


@app.get("/api/health")
def health() -> dict[str, Any]:
    startup_checks = getattr(app.state, "startup_checks", None)
    if startup_checks is None:
        _, rules_bundle = ensure_runtime_artifacts(force=False)
        startup_checks = refresh_startup_checks(app, rules_bundle=rules_bundle)
    return {
        "status": startup_checks["overall_status"],
        "summary": startup_checks["summary"],
        "generated_at": startup_checks["generated_at"],
    }


@app.get("/api/startup-checks")
def api_startup_checks(request: Request) -> dict[str, Any]:
    startup_checks = getattr(app.state, "startup_checks", None)
    if startup_checks is None:
        _, rules_bundle = ensure_runtime_artifacts(force=False)
        startup_checks = refresh_startup_checks(app, rules_bundle=rules_bundle)
    return startup_checks


@app.get("/api/skills")
def api_skills(request: Request) -> list[dict[str, Any]]:
    ensure_runtime_artifacts(force=False)
    return get_skill_manager().list_skills()


@app.get("/api/skill-files")
def api_skill_files(request: Request) -> dict[str, Any]:
    ensure_runtime_artifacts(force=False)
    manager = get_skill_manager()
    items = manager.list_skill_files()
    return {
        "items": [
            {
                **item,
                "modified_at": datetime.fromtimestamp(item["modified_at"]).isoformat(timespec="seconds"),
            }
            for item in items
        ]
    }


@app.get("/api/skill-files/{skill_id}")
def api_skill_file(skill_id: str, request: Request) -> dict[str, Any]:
    ensure_runtime_artifacts(force=False)
    manager = get_skill_manager()
    try:
        return manager.read_skill_file(skill_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/skill-files/{skill_id}")
def api_save_skill_file(skill_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    ensure_runtime_artifacts(force=False)
    content = payload.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="Missing content.")
    manager = get_skill_manager()
    try:
        result = manager.save_skill_file(skill_id, content)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        **result,
        "modified_at": datetime.fromtimestamp(result["modified_at"]).isoformat(timespec="seconds"),
    }


@app.get("/api/config")
def api_config(request: Request) -> dict[str, Any]:
    config, _ = ensure_runtime_artifacts(force=False)
    return config


@app.put("/api/config")
def api_save_config(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _, rules_bundle = ensure_runtime_artifacts(force=True)
    refresh_startup_checks(app, rules_bundle=rules_bundle)
    return api_config()


@app.get("/api/rules")
def api_rules(request: Request) -> dict[str, Any]:
    config, _ = ensure_runtime_artifacts(force=False)
    return parse_rule_bundle(resolve_rule_matrix_path(PROJECT_ROOT, config))


@app.post("/api/generate")
def api_generate(request: Request) -> dict[str, Any]:
    result = build_project_bundle(root=PROJECT_ROOT, config_path=CONFIG_PATH)
    rules_bundle = parse_rule_bundle(resolve_rule_matrix_path(PROJECT_ROOT, result["config"]))
    enabled_skill_groups = set(result["config"].get("generation", {}).get("enabled_skill_groups", []))
    skill_result = generate_approval_item_skills(
        rules_bundle,
        enabled_review_points=enabled_skill_groups or None,
    )
    get_skill_manager().initialize()
    result["approval_skills"] = {
        "generated_count": skill_result["generated_count"],
        "grouping_key": skill_result["grouping_key"],
        "output_dir": skill_result["output_dir"],
    }
    result["approval_item_skills"] = result["approval_skills"]
    refresh_startup_checks(app, rules_bundle=rules_bundle)
    return result


@app.get("/api/outputs")
def api_outputs(request: Request) -> list[dict[str, str]]:
    return list_outputs()


@app.get("/api/approval/sample")
def api_approval_sample() -> dict[str, Any]:
    return load_or_create_sample_document()


@app.get("/api/integration/config")
def api_integration_config(request: Request) -> dict[str, Any]:
    return load_integration_config()


@app.put("/api/integration/config")
def api_save_integration_config(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_integration_config(payload)


@app.post("/api/integration/refresh-token")
def api_refresh_integration_token(request: Request) -> dict[str, Any]:
    client = IworkProjectClient(load_integration_config())
    try:
        token = client.refresh_token()
    except Exception as exc:
        raise to_http_error(exc) from exc
    return {"token": token, "config": load_integration_config()}


@app.get("/api/projects")
def api_projects(
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    keyword: str = "",
    project_name: str = "",
    project_code: str = "",
    domain: str = "",
    department: str = "",
    project_manager: str = "",
    project_type: str = "",
    project_category: str = "",
    fixed_project: str = "",
    project_status: str = "",
    flow_status: str = "",
) -> dict[str, Any]:
    try:
        client = IworkProjectClient(load_integration_config())
        normalized_filters = {
            "project_name": project_name.strip() or keyword.strip(),
            "project_code": project_code.strip(),
            "domain": domain.strip(),
            "department": department.strip(),
            "project_manager": project_manager.strip(),
            "project_type": project_type.strip(),
            "project_category": project_category.strip(),
            "fixed_project": fixed_project.strip(),
            "project_status": project_status.strip(),
            "flow_status": flow_status.strip(),
        }
        remote_filters = {
            "projectName": normalized_filters["project_name"],
        }
        remote_filters = {key: value for key, value in remote_filters.items() if value}
        result = client.list_projects(
            page_num=page_num,
            page_size=page_size,
            filters=remote_filters or None,
        )
        filtered_projects = [item for item in result["projects"] if matches_project_filters(item, normalized_filters)]
        result["projects"] = filtered_projects
        result["filtered_total"] = len(filtered_projects)
        result["filters"] = normalized_filters
        return result
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/project-status-options")
def api_project_status_options() -> dict[str, Any]:
    try:
        client = IworkProjectClient(load_integration_config())
        return {"items": client.list_project_statuses()}
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/files/download")
def api_download_file(path: str = Query(..., min_length=1)) -> Response:
    try:
        client = IworkProjectClient(load_integration_config())
        content, media_type = client.download_file(path)
        return Response(content=content, media_type=media_type)
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/projects/{project_id}/snapshot")
def api_project_snapshot(project_id: str, refresh: bool = False) -> dict[str, Any]:
    try:
        client = IworkProjectClient(load_integration_config())
        return client.fetch_project_snapshot(project_id, force_refresh=refresh)
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/projects/{project_id}/document")
def api_project_document(project_id: str, category: str = DEFAULT_PROJECT_CATEGORY, refresh: bool = False) -> dict[str, Any]:
    try:
        client = IworkProjectClient(load_integration_config())
        requested_category = str(category or "").strip()
        summary = load_cached_project_summary(project_id) or {}
        resolved_category = resolve_project_category_name(requested_category, summary=summary)
        document, _, _ = build_project_document(
            client=client,
            project_id=project_id,
            category=resolved_category,
            refresh=refresh,
        )
        document["requested_category"] = requested_category or resolved_category
        document["resolved_category"] = resolve_project_category_name(requested_category, summary=summary, document=document)
        return document
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/projects/{project_id}/architecture-reviews")
def api_project_architecture_reviews(
    project_id: str,
    category: str = DEFAULT_PROJECT_CATEGORY,
    refresh: bool = False,
) -> dict[str, Any]:
    try:
        client = IworkProjectClient(load_integration_config())
        requested_category = str(category or "").strip()
        summary = load_cached_project_summary(project_id) or {}
        resolved_category = resolve_project_category_name(requested_category, summary=summary)
        return build_architecture_review_payload(
            client=client,
            project_id=project_id,
            category=resolved_category,
            refresh=refresh,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/projects/{project_id}/latest-approval")
def api_project_latest_approval(project_id: str, category: str = DEFAULT_PROJECT_CATEGORY) -> dict[str, Any]:
    try:
        requested_category = str(category or "").strip()
        summary = load_cached_project_summary(project_id) or {}
        resolved_category = resolve_project_category_name(requested_category, summary=summary)
        result = load_latest_remote_approval_result(project_id=project_id, category=resolved_category)
        return {
            "found": result is not None,
            "requested_category": requested_category or resolved_category,
            "resolved_category": resolved_category,
            "result": result,
        }
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/review-feedback")
def api_review_feedback(category: str = DEFAULT_PROJECT_CATEGORY) -> dict[str, Any]:
    try:
        review_items = load_latest_review_feedback_map(category)
        approval_items = load_latest_remote_approval_result_map(category)
        return {"items": merge_review_feedback_with_approvals(review_items, approval_items)}
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.post("/api/review-feedback")
def api_save_review_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="Missing projectId.")

    category = str(payload.get("category") or DEFAULT_PROJECT_CATEGORY).strip() or DEFAULT_PROJECT_CATEGORY
    project_name = str(payload.get("projectName") or payload.get("project_name") or project_id).strip() or project_id
    feedback = payload.get("feedback")
    if not isinstance(feedback, dict):
        raise HTTPException(status_code=400, detail="Missing feedback payload.")

    try:
        return persist_review_feedback(
            project_id=project_id,
            project_name=project_name,
            category=category,
            feedback=feedback,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.post("/api/approve")
def api_approve(payload: dict[str, Any]) -> dict[str, Any]:
    category = payload.get("category")
    document = payload.get("document", payload)
    return evaluate_approval(document=document, category=category)


@app.post("/api/approve/llm")
def api_approve_llm(payload: dict[str, Any]) -> dict[str, Any]:
    project_name = payload.get("project_name") or payload.get("projectName") or "unnamed-project"
    project_id = payload.get("project_id") or payload.get("projectId") or project_name
    category = payload.get("category", DEFAULT_PROJECT_CATEGORY)
    snapshot = payload.get("snapshot") or {"project_id": project_id, "endpoints": {}}
    document = payload.get("document") or payload
    try:
        return run_llm_approval(
            project_name=project_name,
            project_id=project_id,
            category=category,
            snapshot=snapshot,
            document=document,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.post("/api/approve/generated-project")
def api_approve_generated_project(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = payload or {}
    category = resolve_project_category_name(request_payload.get("category"))
    document = normalize_generated_bundle(load_generated_project_bundle(), category)
    return evaluate_approval(document=document, category=category)


@app.post("/api/approve/remote-project")
def api_approve_remote_project(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = payload["projectId"]
    requested_category = str(payload.get("category") or "").strip()
    refresh_document = bool(payload.get("refreshDocument") or payload.get("refresh_document"))
    try:
        client = IworkProjectClient(load_integration_config())
        summary = load_cached_project_summary(project_id) or {}
        category = resolve_project_category_name(requested_category, summary=summary)
        document, snapshot, _ = build_project_document(
            client=client,
            project_id=project_id,
            category=category,
            refresh=refresh_document,
        )
        category = resolve_project_category_name(requested_category, summary=summary, document=document)
        result = run_llm_approval(
            project_name=document.get("project_name") or project_id,
            project_id=project_id,
            category=category,
            snapshot=snapshot,
            document=document,
        )
        result["requested_category"] = requested_category or category
        result["resolved_category"] = category
        return result
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
