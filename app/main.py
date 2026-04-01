"""FastAPI service aligned with the auto_approval-style project layout."""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import shutil
import sys
import threading
import time
from concurrent import futures
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError

from app.approvals.approval_engine import (
    evaluate_approval,
    load_generated_project_bundle,
    load_or_create_sample_document,
    normalize_generated_bundle,
)
from app.approvals.iwork_client import (
    IworkProjectClient,
    RemoteAPIError,
    first_non_empty,
    load_cached_project_snapshot,
    load_cached_project_summary,
    load_integration_config,
    matches_project_filters,
    matches_task_order_filters,
    save_integration_config,
)
from app.approvals.llm_approval_service import run_llm_approval
from app.approvals.project_document_store import load_project_document, persist_project_document
from app.approvals.review_feedback_store import load_latest_review_feedback_map, persist_review_feedback
from app.approvals.remote_project_mapper import map_snapshot_to_document
from app.approvals.category_aliases import CATEGORY_NAME_ALIASES, canonical_category_name
from app.core.llm_client import LLMConfigError, chat_json, load_llm_settings
from app.core.startup_checks import run_startup_checks
from app.core.scenes import normalize_scene
from app.core.paths import (
    ACCEPTANCE_RULES_BUNDLE_PATH,
    ACCEPTANCE_SKILL_MANIFEST_PATH,
    ACCEPTANCE_SKILLS_DIR,
    CONFIG_PATH,
    FRONTEND_DIR,
    INITIATION_SKILLS_DIR,
    LEGACY_APPROVAL_RUNS_DIR,
    LEGACY_SKILL_MANIFEST_PATH,
    PROJECT_ROOT,
    RULES_BUNDLE_PATH,
    SKILL_MANIFEST_PATH,
    SCRIPTS_DIR,
    TASK_ORDER_RULES_BUNDLE_PATH,
    TASK_ORDER_SKILL_MANIFEST_PATH,
    TASK_ORDER_SKILLS_DIR,
    scene_approval_runs_dir,
    scene_generated_dir,
    scene_skills_dir,
    find_acceptance_rule_matrix_path,
    find_rule_matrix_path,
    find_task_order_rule_matrix_path,
)
from app.skills.manager import get_skill_manager

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_project_approval_bundle import build_project_bundle, load_or_create_config, resolve_rule_matrix_path  # noqa: E402
from extract_review_rules import parse_rule_bundle, write_json  # noqa: E402
from generate_approval_item_skills import generate_approval_item_skills  # noqa: E402

LOGGER = logging.getLogger("project_approval.startup")
SCENE_INITIATION = "initiation"
SCENE_ACCEPTANCE = "acceptance"
SCENE_TASK_ORDER = "task_order"
ACCEPTANCE_FILTER_QUERY_TYPES = {
    "domain": 1,
    "project_category": 26,
    "project_type": 4,
    "project_status": 71,
}
DEFAULT_PROJECT_CATEGORY = "工作台开发及实施"
ADMIN_SESSION_COOKIE = "project_approval_admin_session"
ADMIN_SESSION_MAX_AGE = 8 * 60 * 60
_ARCH_REVIEW_CACHE_LOCK = threading.Lock()
_ARCH_REVIEW_CACHE: dict[str, dict[str, Any]] = {}
_REVIEW_FEEDBACK_CACHE_LOCK = threading.Lock()
_REVIEW_FEEDBACK_CACHE: dict[str, dict[str, Any]] = {}
_FRONTEND_DEV_STATUS_LOCK = threading.Lock()
_FRONTEND_DEV_STATUS = {"checked_at": 0.0, "available": False}
FRONTEND_DEV_SERVER_URL = os.getenv("PROJECT_APPROVAL_FRONTEND_DEV_SERVER", "http://127.0.0.1:5173").rstrip("/")
FRONTEND_MODE = os.getenv(
    "PROJECT_APPROVAL_FRONTEND_MODE",
    "dev" if (PROJECT_ROOT / "frontend").exists() else "dist",
).strip().lower()


def log_api_timing(api_name: str, started_at: float, **fields: Any) -> None:
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    extras = " ".join(f"{key}={value}" for key, value in fields.items() if value not in (None, ""))
    LOGGER.info("timing api=%s elapsed_ms=%s %s", api_name, elapsed_ms, extras.strip())


def normalize_list_scene(scene: str | None) -> str:
    normalized = str(scene or "").strip().lower()
    if normalized in {SCENE_TASK_ORDER, "task-order", "taskorder"}:
        return SCENE_TASK_ORDER
    return normalize_scene(scene)


def normalize_skill_scene(scene: str | None) -> str:
    normalized = str(scene or "").strip().lower()
    if normalized in {SCENE_TASK_ORDER, "task-order", "taskorder"}:
        return SCENE_TASK_ORDER
    return normalize_scene(scene)


def acceptance_id_fields(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    budget_project_id = str(payload.get("budget_project_id") or payload.get("budgetProjectId") or "").strip()
    establishment_project_id = str(
        payload.get("establishment_project_id") or payload.get("establishmentProjectId") or ""
    ).strip()
    fields: dict[str, Any] = {}
    if budget_project_id:
        fields["budget_project_id"] = budget_project_id
    if establishment_project_id:
        fields["establishment_project_id"] = establishment_project_id
    return fields


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
    outputs: list[dict[str, str]] = []
    for scene in [SCENE_INITIATION, SCENE_TASK_ORDER, SCENE_ACCEPTANCE]:
        output_dir = scene_generated_dir(scene)
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(output_dir.glob("*")):
            if path.is_file():
                outputs.append(
                    {
                        "name": f"{scene}/{path.name}",
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


ACCEPTANCE_DETAIL_ENDPOINT_KEYS = [
    "acceptance_task_info",
    "acceptance_contract_info",
    "acceptance_stage_tasks",
    "acceptance_stage_contracts",
    "acceptance_count_data",
]


def _acceptance_snapshot_has_detail_endpoints(snapshot: dict[str, Any] | None) -> bool:
    endpoints = (snapshot or {}).get("endpoints") or {}
    if not isinstance(endpoints, dict):
        return False
    return any(key in endpoints for key in ACCEPTANCE_DETAIL_ENDPOINT_KEYS)


def _acceptance_snapshot_has_accept_info(snapshot: dict[str, Any] | None) -> bool:
    endpoints = (snapshot or {}).get("endpoints") or {}
    if not isinstance(endpoints, dict):
        return False
    acceptance_info = (endpoints.get("acceptance_info_list") or {}).get("data")
    return bool(normalize_list(acceptance_info))


def _stale_acceptance_persisted_document(document: dict[str, Any] | None, snapshot: dict[str, Any] | None) -> bool:
    if not _acceptance_snapshot_has_accept_info(snapshot):
        return False
    if _acceptance_snapshot_has_detail_endpoints(snapshot):
        return False
    acceptance = (document or {}).get("acceptance") or {}
    if not isinstance(acceptance, dict):
        return True
    for key in ["task_list", "contract_list", "task_acceptance_list", "contract_acceptance_list", "deliverables"]:
        if normalize_list(acceptance.get(key)):
            return False
    return True


def _stale_acceptance_approval_payload(payload: dict[str, Any]) -> bool:
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
    if not _acceptance_snapshot_has_accept_info(snapshot):
        return False
    return not _acceptance_snapshot_has_detail_endpoints(snapshot)


def architecture_review_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_ARCH_REVIEW_CACHE_TTL", "45") or "45").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 45
    return max(0, min(ttl, 300))


def review_feedback_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_REVIEW_FEEDBACK_CACHE_TTL", "45") or "45").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 45
    return max(0, min(ttl, 300))


def _review_feedback_cache_key(category: str, scene: str = SCENE_INITIATION) -> str:
    return f"{normalize_scene(scene)}:{str(category or '').strip()}"


def _load_cached_review_feedback(category: str, scene: str = SCENE_INITIATION) -> dict[str, Any] | None:
    ttl_seconds = review_feedback_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return None
    cache_key = _review_feedback_cache_key(category, scene)
    if not cache_key:
        return None
    now = time.monotonic()
    with _REVIEW_FEEDBACK_CACHE_LOCK:
        record = _REVIEW_FEEDBACK_CACHE.get(cache_key)
        if not record:
            return None
        if float(record.get("expires_at") or 0) <= now:
            _REVIEW_FEEDBACK_CACHE.pop(cache_key, None)
            return None
        payload = record.get("payload")
        if isinstance(payload, dict):
            return json.loads(json.dumps(payload, ensure_ascii=False))
    return None


def _store_cached_review_feedback(category: str, payload: dict[str, Any], scene: str = SCENE_INITIATION) -> None:
    ttl_seconds = review_feedback_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return
    cache_key = _review_feedback_cache_key(category, scene)
    if not cache_key:
        return
    with _REVIEW_FEEDBACK_CACHE_LOCK:
        _REVIEW_FEEDBACK_CACHE[cache_key] = {
            "expires_at": time.monotonic() + ttl_seconds,
            "payload": json.loads(json.dumps(payload, ensure_ascii=False)),
        }


def _invalidate_review_feedback_cache(category: str, scene: str = SCENE_INITIATION) -> None:
    cache_key = _review_feedback_cache_key(category, scene)
    if not cache_key:
        return
    with _REVIEW_FEEDBACK_CACHE_LOCK:
        _REVIEW_FEEDBACK_CACHE.pop(cache_key, None)


def _architecture_review_cache_key(project_id: str, scene: str = SCENE_INITIATION) -> str:
    return f"{normalize_scene(scene)}:{str(project_id or '').strip()}"


def _load_cached_architecture_reviews(project_id: str, scene: str = SCENE_INITIATION) -> list[dict[str, Any]] | None:
    ttl_seconds = architecture_review_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return None
    cache_key = _architecture_review_cache_key(project_id, scene)
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


def _store_cached_architecture_reviews(
    project_id: str,
    groups: list[dict[str, Any]],
    scene: str = SCENE_INITIATION,
) -> None:
    ttl_seconds = architecture_review_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return
    cache_key = _architecture_review_cache_key(project_id, scene)
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


def _acceptance_tab_config(
    sections: tuple[str, ...],
    project_review_tabs: tuple[str, ...],
    tam_tabs: tuple[str, ...] = (),
) -> dict[str, list[str]]:
    return {
        "sections": list(sections),
        "project_review_tabs": list(project_review_tabs),
        "tam_tabs": list(tam_tabs),
    }


ACCEPTANCE_FIXED_FULL_SECTIONS = (
    "project_review",
    "acceptance_scope",
    "acceptance_stage",
    "acceptance_detail",
    "acceptance_deliverables",
    "architecture_review",
    "tam_models",
)
ACCEPTANCE_FIXED_ARCHITECTURE_SECTIONS = (
    "project_review",
    "acceptance_scope",
    "acceptance_stage",
    "acceptance_detail",
    "acceptance_deliverables",
    "architecture_review",
)
ACCEPTANCE_FIXED_BASE_SECTIONS = (
    "project_review",
    "acceptance_scope",
    "acceptance_stage",
    "acceptance_detail",
    "acceptance_deliverables",
)
ACCEPTANCE_FIXED_PROJECT_REVIEW_OKR_SYSTEM_SCOPE = (
    "background",
    "okr",
    "scope",
    "system_scope",
    "solution",
    "acceptance_plan",
)
ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_SYSTEM_SCOPE = (
    "background",
    "target",
    "scope",
    "system_scope",
    "solution",
    "acceptance_plan",
)
ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_PANORAMA = (
    "background",
    "target",
    "scope",
    "solution",
    "panorama",
    "annual_model",
    "acceptance_plan",
)
ACCEPTANCE_FIXED_TAM_TABS = ("capability", "result", "management")


ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY: dict[str, dict[str, list[str]]] = {}

for _category_name in (
    "\u5de5\u4f5c\u53f0\u5f00\u53d1\u53ca\u5b9e\u65bd",
    "\u4ea7\u54c1\u8fd0\u8425",
    "\u7cfb\u7edf\u4ea7\u54c1\u8d2d\u4e70",
    "\u7cfb\u7edf\u5f00\u53d1\u53ca\u8fd0\u8425",
):
    ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key(_category_name)] = _acceptance_tab_config(
        ACCEPTANCE_FIXED_FULL_SECTIONS,
        ACCEPTANCE_FIXED_PROJECT_REVIEW_OKR_SYSTEM_SCOPE,
        ACCEPTANCE_FIXED_TAM_TABS,
    )

for _category_name in (
    "\u6570\u636e\u8ba2\u9605\u8d2d\u4e70",
    "\u8bbe\u5907\u8d2d\u4e70\u53ca\u5f31\u7535\u5e03\u7ebf",
    "\u8bbe\u5907\u7ef4\u4fee",
):
    ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key(_category_name)] = _acceptance_tab_config(
        ACCEPTANCE_FIXED_ARCHITECTURE_SECTIONS,
        ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_PANORAMA,
    )

for _category_name in (
    "\u5927\u4e00\u7ebf\u8fd0\u7ef4",
    "\u4e09\u7ebf\u8fd0\u7ef4",
    "\u4ea7\u54c1\u7ef4\u4fdd",
    "\u6570\u636e\u4e2d\u5fc3\u7ef4\u62a4",
    "\u57fa\u7840\u670d\u52a1",
    "\u5b89\u5168\u670d\u52a1",
    "\u6570\u636e\u670d\u52a1",
    "\u4fdd\u5bc6\u670d\u52a1",
    "\u7814\u53d1\u5de5\u5177\u8ba2\u9605\u8bb8\u53ef\u5347\u7ea7",
    "\u975e\u7814\u53d1\u5de5\u5177\u8ba2\u9605\u8bb8\u53ef\u5347\u7ea7",
    "\u7814\u53d1\u5de5\u5177\u8bb8\u53ef\u8d2d\u4e70",
    "\u975e\u7814\u53d1\u5de5\u5177\u8bb8\u53ef\u8d2d\u4e70",
    "\u8d44\u6e90\u79df\u8d41",
    "\u673a\u623f\u5efa\u8bbe",
):
    ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key(_category_name)] = _acceptance_tab_config(
        ACCEPTANCE_FIXED_BASE_SECTIONS,
        ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_PANORAMA,
    )

ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key("\u5bf9\u5916\u54a8\u8be2")] = _acceptance_tab_config(
    ACCEPTANCE_FIXED_BASE_SECTIONS,
    ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_SYSTEM_SCOPE,
)


def resolve_acceptance_fixed_tab_config(category: Any) -> dict[str, list[str]]:
    normalized_category = normalize_category_key(canonical_category_name(category))
    default_config = ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY.get(
        normalize_category_key(DEFAULT_PROJECT_CATEGORY),
        _acceptance_tab_config(
            ACCEPTANCE_FIXED_FULL_SECTIONS,
            ACCEPTANCE_FIXED_PROJECT_REVIEW_OKR_SYSTEM_SCOPE,
            ACCEPTANCE_FIXED_TAM_TABS,
        ),
    )
    config = ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY.get(normalized_category, default_config)
    return {
        "sections": list(config["sections"]),
        "project_review_tabs": list(config["project_review_tabs"]),
        "tam_tabs": list(config["tam_tabs"]),
    }


ACCEPTANCE_DYNAMIC_SECTION_KEY_BY_LABEL = {
    "项目回顾": "project_review",
    "专业技术领域评审": "architecture_review",
    "专业技术评审": "architecture_review",
    "tam模型": "tam_models",
    "tam模型评审": "tam_models",
    "验收范围": "acceptance_scope",
    "验收阶段": "acceptance_stage",
    "验收明细": "acceptance_detail",
    "上传备证": "acceptance_deliverables",
    "上传佐证": "acceptance_deliverables",
}

ACCEPTANCE_DYNAMIC_PROJECT_REVIEW_KEY_BY_LABEL = {
    "项目背景": "background",
    "项目目标": "target",
    "项目okr": "okr",
    "项目范围": "scope",
    "系统范围": "system_scope",
    "项目方案": "solution",
    "业务全景图": "panorama",
    "年度管理模型": "annual_model",
    "验收方案": "acceptance_plan",
}

ACCEPTANCE_DYNAMIC_TAM_KEY_BY_LABEL = {
    "能力模型": "capability",
    "能力竞争模型": "capability",
    "结果模型": "result",
    "结果财务客户模型": "result",
    "管理体系模型": "management",
}


def normalize_acceptance_tab_token(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "").strip()).lower()


def normalize_acceptance_tab_config(raw_items: list[dict[str, Any]] | None) -> dict[str, list[str]]:
    def item_order(value: Any) -> tuple[int, int]:
        if not isinstance(value, dict):
            return (1, 10**9)
        candidates = [
            value.get("order"),
            value.get("sort"),
            value.get("sortOrder"),
            value.get("orderNum"),
            value.get("sortNum"),
            value.get("index"),
        ]
        for candidate in candidates:
            try:
                return (0, int(str(candidate).strip()))
            except Exception:
                continue
        return (1, 10**9)

    sections: list[str] = []
    project_review_tabs: list[str] = []
    tam_tabs: list[str] = []
    seen_sections: set[str] = set()
    seen_project_review_tabs: set[str] = set()
    seen_tam_tabs: set[str] = set()

    section_aliases = {
        normalize_acceptance_tab_token(label): key
        for label, key in ACCEPTANCE_DYNAMIC_SECTION_KEY_BY_LABEL.items()
    }
    project_review_aliases = {
        normalize_acceptance_tab_token(label): key
        for label, key in ACCEPTANCE_DYNAMIC_PROJECT_REVIEW_KEY_BY_LABEL.items()
    }
    tam_aliases = {
        normalize_acceptance_tab_token(label): key
        for label, key in ACCEPTANCE_DYNAMIC_TAM_KEY_BY_LABEL.items()
    }

    def collect_item(item: dict[str, Any]) -> None:
        candidates = [
            item.get("label"),
            item.get("name"),
            item.get("text"),
            item.get("title"),
            item.get("tab"),
            item.get("tabName"),
            item.get("classifyName"),
            item.get("reviewPoint"),
            item.get("reviewPointName"),
            item.get("bcName"),
            item.get("content"),
        ]
        for candidate in candidates:
            token = normalize_acceptance_tab_token(candidate)
            if not token:
                continue
            section_key = section_aliases.get(token)
            if section_key and section_key not in seen_sections:
                seen_sections.add(section_key)
                sections.append(section_key)
            project_review_key = project_review_aliases.get(token)
            if project_review_key and project_review_key not in seen_project_review_tabs:
                seen_project_review_tabs.add(project_review_key)
                project_review_tabs.append(project_review_key)
            tam_key = tam_aliases.get(token)
            if tam_key and tam_key not in seen_tam_tabs:
                seen_tam_tabs.add(tam_key)
                tam_tabs.append(tam_key)

    def walk_items(items: list[dict[str, Any]] | None) -> None:
        for item in sorted((items or []), key=item_order):
            if not isinstance(item, dict):
                continue
            collect_item(item)
            for child_key in ("subTabList", "subTabs", "children"):
                child_items = item.get(child_key)
                if isinstance(child_items, list):
                    walk_items(child_items)

    walk_items(raw_items)

    return {
        "sections": sections,
        "project_review_tabs": project_review_tabs,
        "tam_tabs": tam_tabs,
    }


def known_category_lookup(scene: str = SCENE_INITIATION) -> dict[str, str]:
    _, rules_bundle = ensure_scene_artifacts(scene, force=False)
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
    scene: str = SCENE_INITIATION,
) -> str:
    category_lookup = known_category_lookup(scene=scene)
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
    return category_lookup.get(
        normalize_category_key(DEFAULT_PROJECT_CATEGORY),
        next(iter(category_lookup.values()), DEFAULT_PROJECT_CATEGORY),
    )


def load_latest_remote_approval_result(
    project_id: str,
    category: str,
    scene: str = SCENE_INITIATION,
) -> dict[str, Any] | None:
    normalized_scene = normalize_scene(scene)
    run_dirs = [scene_approval_runs_dir(normalized_scene)]
    if normalized_scene == SCENE_INITIATION:
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
            if str(payload.get("category") or DEFAULT_PROJECT_CATEGORY) != category:
                continue
            if normalize_scene(payload.get("scene")) != normalized_scene:
                continue
            if _stale_acceptance_approval_payload(payload):
                continue

            generated_at = parse_iso_datetime(payload.get("generated_at"))
            sort_timestamp = generated_at.timestamp() if generated_at else result_path.stat().st_mtime
            if sort_timestamp >= latest_timestamp:
                latest_timestamp = sort_timestamp
                latest_payload = payload

    return latest_payload


def load_latest_remote_approval_result_any_category(
    project_id: str,
    scene: str = SCENE_INITIATION,
) -> dict[str, Any] | None:
    normalized_scene = normalize_scene(scene)
    run_dirs = [scene_approval_runs_dir(normalized_scene)]
    if normalized_scene == SCENE_INITIATION:
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
            if _stale_acceptance_approval_payload(payload):
                continue

            generated_at = parse_iso_datetime(payload.get("generated_at"))
            sort_timestamp = generated_at.timestamp() if generated_at else result_path.stat().st_mtime
            if sort_timestamp >= latest_timestamp:
                latest_timestamp = sort_timestamp
                latest_payload = payload

    return latest_payload


def load_latest_remote_approval_result_map(
    category: str,
    scene: str = SCENE_INITIATION,
) -> dict[str, dict[str, Any]]:
    normalized_scene = normalize_scene(scene)
    run_dirs = [scene_approval_runs_dir(normalized_scene)]
    if normalized_scene == SCENE_INITIATION:
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
            if str(payload.get("category") or DEFAULT_PROJECT_CATEGORY) != category:
                continue
            if normalize_scene(payload.get("scene")) != normalized_scene:
                continue
            if _stale_acceptance_approval_payload(payload):
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


def to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RemoteAPIError):
        return HTTPException(status_code=502, detail=f"远程接口返回错误[{exc.code}]: {exc.message}")
    return HTTPException(status_code=502, detail=str(exc))


def is_llm_unavailable_error(exc: Exception) -> bool:
    return isinstance(exc, (APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError))


def build_deterministic_approval_fallback(
    *,
    project_name: str,
    project_id: str,
    category: str,
    scene: str,
    document: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    baseline = evaluate_approval(document=document, category=category, scene=scene)
    failed_items = [item for item in (baseline.get("findings") or []) if str(item.get("status") or "").strip() == "fail"]
    failed_labels = [
        str(item.get("review_content") or item.get("review_point") or "").strip()
        for item in failed_items
        if str(item.get("review_content") or item.get("review_point") or "").strip()
    ]
    pass_decision = str(baseline.get("decision") or "").strip() == "通过"
    if pass_decision:
        summary = "LLM审批暂不可用，已自动降级为规则引擎审批结果。当前规则校验通过。"
    elif failed_labels:
        summary = f"LLM审批暂不可用，已自动降级为规则引擎审批结果。当前需关注：{'、'.join(failed_labels[:6])}。"
    else:
        summary = "LLM审批暂不可用，已自动降级为规则引擎审批结果。"

    return {
        "project_name": project_name,
        "project_id": project_id,
        "category": category,
        "scene": scene,
        "document_source": document.get("document_source") or "unknown",
        "document_saved_at": document.get("document_saved_at"),
        "decision": baseline.get("decision") or "需补充材料",
        "summary": summary,
        "item_results": baseline.get("rule_results") or [],
        "risks": [] if pass_decision else failed_labels[:10],
        "missing_information": [] if pass_decision else failed_labels[:10],
        "positive_evidence": [],
        "project_commentary": "",
        "baseline": baseline,
        "segments": [],
        "run_dir": "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "decision_source": "deterministic_fallback",
        "fallback_reason": reason,
    }


def should_rebuild_bundle(rule_matrix_path: Path) -> bool:
    return not RULES_BUNDLE_PATH.exists() or RULES_BUNDLE_PATH.stat().st_mtime < rule_matrix_path.stat().st_mtime


def should_regenerate_skills(
    rule_matrix_path: Path,
    *,
    manifest_path: Path,
    skills_dir: Path,
) -> bool:
    if not manifest_path.exists():
        return True
    if manifest_path.stat().st_mtime < rule_matrix_path.stat().st_mtime:
        return True
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return True
    expected_root = skills_dir.resolve()
    for skill in payload.get("skills", []):
        directory_raw = str(skill.get("directory", "")).strip()
        if not directory_raw:
            return True
        directory = Path(directory_raw).resolve()
        if directory != expected_root and expected_root not in directory.parents:
            return True
        if not directory.exists():
            return True
    return False


def migrate_legacy_initiation_skills() -> None:
    INITIATION_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for legacy_dir in sorted(scene_skills_dir(SCENE_INITIATION).parent.glob("approval-*")):
        if not legacy_dir.is_dir():
            continue
        target_dir = INITIATION_SKILLS_DIR / legacy_dir.name
        if target_dir.exists():
            continue
        shutil.move(str(legacy_dir), str(target_dir))
    if LEGACY_SKILL_MANIFEST_PATH.exists() and not SKILL_MANIFEST_PATH.exists():
        SKILL_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_SKILL_MANIFEST_PATH, SKILL_MANIFEST_PATH)


def normalize_runtime_generation_paths(config: dict[str, Any]) -> dict[str, Any]:
    generation = config.setdefault("generation", {})
    output_dir = Path(str(generation.get("output_dir", "runtime") or "runtime")).as_posix().rstrip("/")
    rules_output = Path(str(generation.get("rules_output", "runtime/review_rules.json") or "runtime/review_rules.json")).as_posix()
    changed = False
    if output_dir in {"runtime", ".", ""}:
        generation["output_dir"] = "runtime/initiation"
        changed = True
    if rules_output in {"review_rules.json", "runtime/review_rules.json"}:
        generation["rules_output"] = "runtime/initiation/review_rules.json"
        changed = True
    if changed:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def ensure_runtime_artifacts(*, force: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    migrate_legacy_initiation_skills()
    rule_matrix_path = find_rule_matrix_path()
    bootstrap_rules = parse_rule_bundle(rule_matrix_path)
    config = load_or_create_config(CONFIG_PATH, PROJECT_ROOT, bootstrap_rules)
    config = normalize_runtime_generation_paths(config)
    rule_source_path = resolve_rule_matrix_path(PROJECT_ROOT, config)
    rules_bundle = parse_rule_bundle(rule_source_path)

    if force or should_rebuild_bundle(rule_source_path):
        build_project_bundle(root=PROJECT_ROOT, config_path=CONFIG_PATH)
        rules_bundle = parse_rule_bundle(rule_source_path)

    if force or should_regenerate_skills(
        rule_source_path,
        manifest_path=SKILL_MANIFEST_PATH,
        skills_dir=INITIATION_SKILLS_DIR,
    ):
        enabled_skill_groups = set(config.get("generation", {}).get("enabled_skill_groups", []))
        generate_approval_item_skills(
            rules_bundle,
            output_dir=INITIATION_SKILLS_DIR,
            enabled_review_points=enabled_skill_groups or None,
        )

    get_skill_manager(SCENE_INITIATION).initialize()
    return config, rules_bundle


def ensure_acceptance_artifacts(*, force: bool = False) -> dict[str, Any]:
    rule_source_path = find_acceptance_rule_matrix_path()
    rules_bundle = parse_rule_bundle(rule_source_path)

    if force or not ACCEPTANCE_RULES_BUNDLE_PATH.exists() or (
        ACCEPTANCE_RULES_BUNDLE_PATH.stat().st_mtime < rule_source_path.stat().st_mtime
    ):
        write_json(ACCEPTANCE_RULES_BUNDLE_PATH, rules_bundle)

    if force or should_regenerate_skills(
        rule_source_path,
        manifest_path=ACCEPTANCE_SKILL_MANIFEST_PATH,
        skills_dir=ACCEPTANCE_SKILLS_DIR,
    ):
        generate_approval_item_skills(
            rules_bundle,
            output_dir=ACCEPTANCE_SKILLS_DIR,
        )

    get_skill_manager(SCENE_ACCEPTANCE).initialize()
    return rules_bundle


def ensure_task_order_artifacts(*, force: bool = False) -> dict[str, Any]:
    rule_source_path = find_task_order_rule_matrix_path()
    rules_bundle = parse_rule_bundle(rule_source_path)

    if force or not TASK_ORDER_RULES_BUNDLE_PATH.exists() or (
        TASK_ORDER_RULES_BUNDLE_PATH.stat().st_mtime < rule_source_path.stat().st_mtime
    ):
        write_json(TASK_ORDER_RULES_BUNDLE_PATH, rules_bundle)

    if force or should_regenerate_skills(
        rule_source_path,
        manifest_path=TASK_ORDER_SKILL_MANIFEST_PATH,
        skills_dir=TASK_ORDER_SKILLS_DIR,
    ):
        generate_approval_item_skills(
            rules_bundle,
            output_dir=TASK_ORDER_SKILLS_DIR,
        )

    get_skill_manager(SCENE_TASK_ORDER).initialize()
    return rules_bundle


def ensure_scene_artifacts(scene: str = SCENE_INITIATION, *, force: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_scene = normalize_skill_scene(scene)
    if normalized_scene == SCENE_TASK_ORDER:
        return {}, ensure_task_order_artifacts(force=force)
    if normalized_scene == SCENE_ACCEPTANCE:
        return {}, ensure_acceptance_artifacts(force=force)
    return ensure_runtime_artifacts(force=force)


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
    scene: str = SCENE_INITIATION,
    refresh: bool = False,
    include_architecture_reviews: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    started_at = time.perf_counter()
    normalized_scene = normalize_scene(scene)
    cached_record = None if refresh else load_project_document(project_id, category, scene=normalized_scene)
    if cached_record:
        cached_document = dict(cached_record.get("document") or {})
        cached_document["document_source"] = str(cached_record.get("source") or "persisted")
        cached_document["document_saved_at"] = cached_record.get("saved_at")
        cached_snapshot = cached_record.get("snapshot") or cached_document.get("remote_snapshot") or {"project_id": project_id, "endpoints": {}}
        if include_architecture_reviews:
            cached_groups = cached_document.get("architecture_review_details")
            snapshot_groups = (
                collect_acceptance_architecture_review_groups(cached_document)
                if normalized_scene == SCENE_ACCEPTANCE
                else _build_architecture_review_groups_from_snapshot(cached_snapshot)
            )
            if not _architecture_review_groups_have_material(cached_groups) and _architecture_review_groups_have_material(snapshot_groups):
                cached_groups = snapshot_groups
            if not isinstance(cached_groups, list) or not cached_groups:
                cached_groups = _load_cached_architecture_reviews(project_id, normalized_scene)
            if not _architecture_review_groups_have_material(cached_groups) and isinstance(snapshot_groups, list) and snapshot_groups:
                cached_groups = snapshot_groups
            if isinstance(cached_groups, list) and cached_groups:
                _store_cached_architecture_reviews(project_id, cached_groups, normalized_scene)
                cached_document["architecture_reviews"] = review_groups_to_document_fields(cached_groups)
                cached_document["architecture_review_details"] = cached_groups
        if normalized_scene == SCENE_ACCEPTANCE and _stale_acceptance_persisted_document(cached_document, cached_snapshot):
            cached_document = None
        else:
            if normalized_scene == SCENE_ACCEPTANCE:
                cached_document["debug_ids"] = {
                    "budget_project_id": str(cached_snapshot.get("budget_project_id") or project_id),
                    "establishment_project_id": str(cached_snapshot.get("establishment_project_id") or project_id),
                }
            cached_document["scene"] = normalized_scene
            log_api_timing(
                "build_project_document",
                started_at,
                project_id=project_id,
                scene=normalized_scene,
                refresh=refresh,
                include_architecture_reviews=include_architecture_reviews,
                source="persisted",
                **acceptance_id_fields(cached_snapshot if normalized_scene == SCENE_ACCEPTANCE else None),
            )
            return cached_document, cached_snapshot, "persisted"

    remote_snapshot = client.fetch_project_snapshot(
        project_id,
        scene=normalized_scene,
        force_refresh=refresh,
        category=category,
    )
    api_cache_snapshot = load_cached_project_snapshot(project_id, scene=normalized_scene) if normalized_scene != SCENE_ACCEPTANCE else None
    snapshot = merge_project_snapshots(remote_snapshot, api_cache_snapshot)
    source = "remote" if snapshot_has_usable_data(remote_snapshot) else "api_result_cache"
    if not snapshot_has_usable_data(snapshot):
        source = "remote"

    project_summary = load_cached_project_summary(project_id, scene=normalized_scene) or {"id": project_id}
    document = map_snapshot_to_document(snapshot, project_summary, category)
    if include_architecture_reviews:
        architecture_review_groups = None if refresh else _load_cached_architecture_reviews(project_id, normalized_scene)
        snapshot_groups = (
            collect_acceptance_architecture_review_groups(document)
            if normalized_scene == SCENE_ACCEPTANCE
            else _build_architecture_review_groups_from_snapshot(snapshot)
        )
        if not _architecture_review_groups_have_material(architecture_review_groups) and _architecture_review_groups_have_material(snapshot_groups):
            architecture_review_groups = snapshot_groups
        if architecture_review_groups is None:
            architecture_review_groups = snapshot_groups
        if not _architecture_review_groups_have_material(architecture_review_groups) and normalized_scene != SCENE_ACCEPTANCE:
            architecture_review_groups = collect_architecture_review_groups(
                client=client,
                project_id=project_id,
                snapshot=snapshot,
            )
        if architecture_review_groups is None:
            architecture_review_groups = []
        if architecture_review_groups:
            _store_cached_architecture_reviews(project_id, architecture_review_groups, normalized_scene)
        document["architecture_reviews"] = review_groups_to_document_fields(architecture_review_groups)
        document["architecture_review_details"] = architecture_review_groups
    if normalized_scene == SCENE_ACCEPTANCE:
        document["debug_ids"] = {
            "budget_project_id": str(snapshot.get("budget_project_id") or project_id),
            "establishment_project_id": str(snapshot.get("establishment_project_id") or project_id),
        }
    document["document_source"] = source
    document["scene"] = normalized_scene
    document["document_saved_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    persist_project_document(
        project_id=project_id,
        category=category,
        scene=normalized_scene,
        document=document,
        source=source,
        snapshot=snapshot,
        project_summary=project_summary,
    )
    log_api_timing(
        "build_project_document",
        started_at,
        project_id=project_id,
        scene=normalized_scene,
        refresh=refresh,
        include_architecture_reviews=include_architecture_reviews,
        source=source,
        **acceptance_id_fields(snapshot if normalized_scene == SCENE_ACCEPTANCE else None),
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
    if normalized in {"0", "不涉及", "not involved", "NOT INVOLVED"}:
        return "不涉及"
    if normalized in {"不通过", "fail", "FAIL"}:
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


def _normalize_technology_review_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ["dimensionList", "checkList", "checklist", "reviewResultList", "list", "items"]:
            nested = data.get(key)
            if nested not in (None, "", []):
                items = _normalize_review_items(nested)
                if items:
                    return items
        review_result = data.get("reviewResult")
        if isinstance(review_result, (list, dict)) and review_result not in ({}, []):
            items = _normalize_review_items(review_result)
            if items:
                return items
    return _normalize_review_items(data)


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
            items = _normalize_technology_review_items(data)
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


def _snapshot_endpoint_payload(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    endpoints = snapshot.get("endpoints") or {}
    payload = endpoints.get(key)
    return payload if isinstance(payload, dict) else {}


def _build_architecture_review_groups_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    product_context = _extract_product_context(snapshot)

    business_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_business")
    business_items = _normalize_review_items(business_payload.get("data"))
    info_architecture_items = [item for item in business_items if _is_information_architecture_item(item)]
    business_items = [item for item in business_items if not _is_information_architecture_item(item)]
    business_group = {
        "key": "business",
        "title": "业务架构评审状态",
        "link_label": "前往EAMAP查看",
        "ok": bool(business_items),
        "message": str(business_payload.get("message") or ""),
        "summary": _build_business_review_summary(snapshot),
        "items": business_items,
        "context": product_context,
    }

    data_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_data")
    data_items = _normalize_review_items(data_payload.get("data"))
    merged_data_items = info_architecture_items + data_items
    data_message = str(data_payload.get("message") or "")
    if info_architecture_items:
        data_message = f"{data_message} Merged information-architecture items from business review.".strip()
    data_group = {
        "key": "data",
        "title": "数据架构评审状态",
        "link_label": "前往信息架构中心查看",
        "ok": bool(merged_data_items),
        "message": data_message,
        "summary": {
            "flow_dimension_count": len({item.get("dimension") for item in merged_data_items if item.get("dimension")}),
            "check_point_count": len(merged_data_items),
        },
        "items": merged_data_items,
    }

    technology_group = _build_review_error_group("technology", "技术架构评审状态", "前往云原生查看", "")
    fallback_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_technology_fallback")
    fallback_items = _normalize_review_items(fallback_payload.get("data"))
    technology_candidates: list[dict[str, Any]] = []
    for type_value in [1, 2, 3, 4, 5, 6]:
        payload = _snapshot_endpoint_payload(snapshot, f"architecture_review_technology_type_{type_value}")
        if not payload:
            continue
        data = payload.get("data") or {}
        items = _normalize_technology_review_items(data)
        technology_candidates.append(
            {
                "type": type_value,
                "payload": payload,
                "data": data,
                "items": items,
            }
        )
    chosen_technology = next(
        (
            candidate
            for candidate in technology_candidates
            if candidate["payload"].get("code") == 200
            and (
                candidate["items"]
                or int((candidate["data"] or {}).get("appCount") or 0)
                or int((candidate["data"] or {}).get("serviceCount") or 0)
            )
        ),
        None,
    )
    if chosen_technology and chosen_technology["items"]:
        chosen_data = chosen_technology.get("data") or {}
        payload = chosen_technology.get("payload") or {}
        technology_group = {
            "key": "technology",
            "title": "技术架构评审状态",
            "link_label": "前往云原生查看",
            "ok": True,
            "message": str(payload.get("message") or ""),
            "summary": {
                "app_count": int(chosen_data.get("appCount") or 0),
                "service_count": int(chosen_data.get("serviceCount") or 0),
                "type": chosen_technology.get("type"),
            },
            "items": chosen_technology["items"],
        }
    elif fallback_items:
        technology_group = {
            "key": "technology",
            "title": "技术架构评审状态",
            "link_label": "前往云原生查看",
            "ok": True,
            "message": str(
                fallback_payload.get("message")
                or "技术架构评审接口未返回明细，已回退使用系统范围(dataType=1)内容作为技术架构材料。"
            ),
            "summary": {
                "app_count": 0,
                "service_count": len(fallback_items),
                "type": "fallback",
            },
            "items": fallback_items,
        }

    security_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_security")
    security_data = security_payload.get("data") or {}
    security_items = _normalize_review_items(security_data)
    security_group = {
        "key": "security",
        "title": "安全架构评审状态",
        "link_label": "前往应用开发安全平台查看",
        "ok": bool(security_items),
        "message": str(security_payload.get("message") or ""),
        "summary": {
            "app_count": int(security_data.get("appCount") or 0),
            "service_count": int(security_data.get("serviceCount") or 0),
            "safety_level": str(security_data.get("safetyLevel") or ""),
        },
        "items": security_items,
    }

    return [business_group, data_group, technology_group, security_group]


def _architecture_review_groups_have_material(groups: list[dict[str, Any]] | None) -> bool:
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


def _acceptance_review_group_key(item: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            str(item.get("dimension") or ""),
            str(item.get("checkpoint") or ""),
            str(item.get("value_model") or ""),
            str(item.get("description") or ""),
        ]
    ).lower()
    if any(keyword in haystack for keyword in ["security", "safe", "安全"]):
        return "security"
    if any(keyword in haystack for keyword in ["data", "信息", "数据", "模型", "对象"]):
        return "data"
    if any(keyword in haystack for keyword in ["business", "eamap", "流程", "业务", "okr"]):
        return "business"
    if any(keyword in haystack for keyword in ["technology", "tech", "技术", "架构", "应用", "微服务", "cloud", "云"]):
        return "technology"
    return "technology"


def _build_acceptance_review_group(
    key: str,
    title: str,
    link_label: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, Any]
    if key == "business":
        summary = {
            "business_process_count": len(items),
            "business_object_count": len(
                {str(item.get("checkpoint") or "").strip() for item in items if str(item.get("checkpoint") or "").strip()}
            ),
        }
    elif key == "data":
        summary = {
            "flow_dimension_count": len({str(item.get("dimension") or "").strip() for item in items if str(item.get("dimension") or "").strip()}),
            "check_point_count": len(items),
        }
    else:
        summary = {"service_count": len(items)}
    return {
        "key": key,
        "title": title,
        "link_label": link_label,
        "ok": len(items) > 0,
        "message": "" if items else "No acceptance review items were returned for this dimension.",
        "summary": summary,
        "items": items,
    }


def collect_acceptance_architecture_review_groups(document: dict[str, Any]) -> list[dict[str, Any]]:
    acceptance = document.get("acceptance") or {}
    raw_items = normalize_list(acceptance.get("architecture_elements"))
    normalized_items: list[dict[str, Any]] = []
    for index, row in enumerate(raw_items, start=1):
        if not isinstance(row, dict):
            continue
        normalized_items.append(
            {
                "id": str(row.get("id") or f"acceptance-review-{index}"),
                "index": int(row.get("index") or index),
                "dimension": _pick_text(row, "dimension", "dimensionName", "typeName", "type"),
                "checkpoint": _pick_text(row, "checkpoint", "checkPoint", "checkpointName", "name", "title"),
                "value_model": _pick_text(
                    row,
                    "value_model",
                    "valueModel",
                    "reviewModel",
                    "reviewStandard",
                    "reviewContent",
                    "content",
                    "description",
                ),
                "reviewer": _pick_text(
                    row,
                    "reviewer",
                    "reviewerName",
                    "initialReviewer",
                    "creator",
                    "createUser",
                    "auditUser",
                ),
                "conclusion": _normalize_review_conclusion(
                    _pick_text(
                        row,
                        "conclusion",
                        "reviewConclusion",
                        "reviewResultName",
                        "reviewResult",
                        "preliminaryConclusion",
                        "result",
                        "statusName",
                        "status",
                    )
                ),
                "description": _pick_text(row, "description", "reviewDescription", "remark", "opinion", "detail"),
            }
        )

    grouped_items: dict[str, list[dict[str, Any]]] = {
        "business": [],
        "data": [],
        "technology": [],
        "security": [],
    }
    for item in normalized_items:
        grouped_items[_acceptance_review_group_key(item)].append(item)

    return [
        _build_acceptance_review_group("business", "Business Architecture Review", "Open Acceptance Review", grouped_items["business"]),
        _build_acceptance_review_group("data", "Data Architecture Review", "Open Acceptance Review", grouped_items["data"]),
        _build_acceptance_review_group(
            "technology",
            "Technology Architecture Review",
            "Open Acceptance Review",
            grouped_items["technology"],
        ),
        _build_acceptance_review_group("security", "Security Architecture Review", "Open Acceptance Review", grouped_items["security"]),
    ]


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
    scene: str = SCENE_INITIATION,
    refresh: bool = False,
) -> dict[str, Any]:
    normalized_scene = normalize_scene(scene)
    document, snapshot, source = build_project_document(
        client=client,
        project_id=project_id,
        category=category,
        scene=normalized_scene,
        refresh=refresh,
    )
    cached_groups = document.get("architecture_review_details")
    if not refresh and isinstance(cached_groups, list) and cached_groups:
        groups = cached_groups
    else:
        groups = None if refresh else _load_cached_architecture_reviews(project_id, normalized_scene)
        if groups is None:
            if normalized_scene == SCENE_ACCEPTANCE:
                groups = collect_acceptance_architecture_review_groups(document)
            else:
                groups = collect_architecture_review_groups(
                    client=client,
                    project_id=project_id,
                    snapshot=snapshot,
                )
            _store_cached_architecture_reviews(project_id, groups, normalized_scene)
    return {
        "project_id": project_id,
        "project_name": document.get("project_name") or project_id,
        "document_source": source,
        "scene": normalized_scene,
        "debug_ids": document.get("debug_ids") or acceptance_id_fields(snapshot if normalized_scene == SCENE_ACCEPTANCE else None),
        "groups": groups,
    }


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    ensure_admin_sessions(app_instance)
    _, rules_bundle = ensure_runtime_artifacts(force=False)
    try:
        ensure_acceptance_artifacts(force=False)
    except Exception as exc:
        LOGGER.warning("Acceptance artifacts are unavailable during startup: %s", exc)
    checks = refresh_startup_checks(app_instance, rules_bundle=rules_bundle)
    if checks["overall_status"] == "error":
        raise RuntimeError("Critical startup checks failed. See runtime/startup_checks.json for details.")
    yield


app = FastAPI(title="Project Approval API", version="0.4.0", lifespan=lifespan)


def active_frontend_dir() -> Path:
    if FRONTEND_DIR.exists():
        return FRONTEND_DIR
    raise HTTPException(
        status_code=503,
        detail="Frontend build assets not found. Run `cd frontend && npm run build`.",
    )


def frontend_index_file() -> Path:
    return active_frontend_dir() / "index.html"


def frontend_source_dir() -> Path:
    return PROJECT_ROOT / "frontend"


def frontend_dev_mode_enabled() -> bool:
    if FRONTEND_MODE == "dist":
        return False
    if FRONTEND_MODE == "dev":
        return True
    return frontend_source_dir().exists()


def ensure_frontend_dev_server() -> None:
    if FRONTEND_MODE == "dev" and not frontend_dev_server_available():
        raise HTTPException(
            status_code=503,
            detail="Frontend dev server not found. Run `cd frontend && npm run dev`.",
        )


def frontend_dev_server_available() -> bool:
    if not frontend_dev_mode_enabled():
        return False

    now = time.monotonic()
    with _FRONTEND_DEV_STATUS_LOCK:
        if now - float(_FRONTEND_DEV_STATUS["checked_at"]) < 2:
            return bool(_FRONTEND_DEV_STATUS["available"])

    probe_url = f"{FRONTEND_DEV_SERVER_URL}/ui/"
    available = False
    try:
        with urlopen(probe_url, timeout=0.35) as response:
            available = response.status < 500
    except (OSError, URLError):
        available = False

    with _FRONTEND_DEV_STATUS_LOCK:
        _FRONTEND_DEV_STATUS["checked_at"] = now
        _FRONTEND_DEV_STATUS["available"] = available

    return available


def frontend_dev_redirect(path: str = "", query: str = "") -> RedirectResponse:
    normalized_path = path.strip("/")
    url = f"{FRONTEND_DEV_SERVER_URL}/ui"
    if normalized_path:
        url = f"{url}/{normalized_path}"
    elif path.endswith("/"):
        url = f"{url}/"
    if query:
        url = f"{url}?{query}"
    return RedirectResponse(url=url, status_code=307)


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
    return RedirectResponse(url="/ui/initiation")


@app.get("/ui")
@app.get("/ui/")
def ui_root(request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path="/" if request.url.path.endswith("/") else "", query=request.url.query)
    return FileResponse(frontend_index_file())


@app.get("/ui/index.html", include_in_schema=False)
def ui_legacy_index() -> RedirectResponse:
    return RedirectResponse(url="/ui/initiation")


@app.get("/ui/approval", include_in_schema=False)
def ui_approval() -> Response:
    return RedirectResponse(url="/ui/initiation/projects")


@app.get("/ui/approval.html", include_in_schema=False)
def ui_legacy_approval() -> Response:
    return RedirectResponse(url="/ui/initiation/projects")


@app.get("/ui/workbench.html", include_in_schema=False)
def ui_legacy_workbench(projectId: str | None = None) -> Response:
    query = f"?projectId={projectId}" if projectId else ""
    return RedirectResponse(url=f"/ui/workbench{query}")


@app.get("/ui/workbench", include_in_schema=False)
def ui_workbench(request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path="workbench", query=request.url.query)
    return FileResponse(frontend_index_file())


@app.get("/ui/skills.html", include_in_schema=False)
def ui_legacy_skills() -> Response:
    return RedirectResponse(url="/ui/initiation/skills")


@app.get("/ui/rules.html", include_in_schema=False)
def ui_legacy_rules() -> Response:
    return RedirectResponse(url="/ui/initiation/skills")


@app.get("/ui/project-viewer.html", include_in_schema=False)
def ui_legacy_project_viewer(
    projectId: str,
    category: str | None = None,
    scene: str | None = None,
) -> Response:
    query_params: dict[str, str] = {}
    if category:
        query_params["category"] = category
    if scene:
        query_params["scene"] = normalize_scene(scene)
    query = f"?{urlencode(query_params)}" if query_params else ""
    return RedirectResponse(url=f"/ui/project/{projectId}{query}")


@app.get("/ui/project/{project_id}", include_in_schema=False)
def ui_project(project_id: str, request: Request, category: str | None = None) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path=f"project/{project_id}", query=request.url.query)
    return FileResponse(frontend_index_file())


@app.get("/ui/skills", include_in_schema=False)
def ui_skills() -> Response:
    return RedirectResponse(url="/ui/initiation/skills")


@app.get("/ui/initiation", include_in_schema=False)
@app.get("/ui/acceptance", include_in_schema=False)
@app.get("/ui/task-order", include_in_schema=False)
@app.get("/ui/initiation/projects", include_in_schema=False)
@app.get("/ui/initiation/review-feedback", include_in_schema=False)
@app.get("/ui/initiation/skills", include_in_schema=False)
@app.get("/ui/acceptance/projects", include_in_schema=False)
@app.get("/ui/acceptance/review-feedback", include_in_schema=False)
@app.get("/ui/acceptance/skills", include_in_schema=False)
@app.get("/ui/task-order/projects", include_in_schema=False)
@app.get("/ui/task-order/review-feedback", include_in_schema=False)
@app.get("/ui/task-order/skills", include_in_schema=False)
def ui_scene_pages(request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path=request.url.path.removeprefix("/ui/"), query=request.url.query)
    return FileResponse(frontend_index_file())


@app.get("/ui/{full_path:path}", include_in_schema=False)
def ui_files(full_path: str, request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path=full_path, query=request.url.query)
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
def api_skills(request: Request, scene: str = SCENE_INITIATION) -> list[dict[str, Any]]:
    normalized_scene = normalize_skill_scene(scene)
    ensure_scene_artifacts(normalized_scene, force=False)
    return get_skill_manager(normalized_scene).list_skills()


@app.get("/api/skill-files")
def api_skill_files(request: Request, scene: str = SCENE_INITIATION) -> dict[str, Any]:
    normalized_scene = normalize_skill_scene(scene)
    ensure_scene_artifacts(normalized_scene, force=False)
    manager = get_skill_manager(normalized_scene)
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
def api_skill_file(skill_id: str, request: Request, scene: str = SCENE_INITIATION) -> dict[str, Any]:
    normalized_scene = normalize_skill_scene(scene)
    ensure_scene_artifacts(normalized_scene, force=False)
    manager = get_skill_manager(normalized_scene)
    try:
        return manager.read_skill_file(skill_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/skill-files/{skill_id}")
def api_save_skill_file(
    skill_id: str,
    payload: dict[str, Any],
    request: Request,
    scene: str = SCENE_INITIATION,
) -> dict[str, Any]:
    normalized_scene = normalize_skill_scene(scene)
    ensure_scene_artifacts(normalized_scene, force=False)
    content = payload.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="Missing content.")
    manager = get_skill_manager(normalized_scene)
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
def api_rules(request: Request, scene: str = SCENE_INITIATION) -> dict[str, Any]:
    _, rules_bundle = ensure_scene_artifacts(normalize_skill_scene(scene), force=False)
    return rules_bundle


@app.get("/api/projects/{project_id}/acceptance-tabs")
def api_project_acceptance_tabs(
    project_id: str,
    param_code: str = "",
) -> dict[str, Any]:
    started_at = time.perf_counter()
    raw_items: list[dict[str, Any]] = []
    resolved_param_code = ""
    resolved_base_project_id = ""
    resolved_category = ""
    ok = True
    message = ""
    try:
        client = IworkProjectClient(load_integration_config())
        resolved_ids = client.resolve_acceptance_project_ids(project_id)
        resolved_base_project_id = str(
            first_non_empty(
                resolved_ids.get("establishment_project_id"),
                project_id,
            )
            or ""
        ).strip()
        base_info = client.get_project_base_info(resolved_base_project_id, scene=SCENE_ACCEPTANCE)
        resolved_param_code = str(first_non_empty(param_code, base_info.get("paramCode")) or "").strip()
        resolved_category = resolve_project_category_name(summary=base_info, scene=SCENE_ACCEPTANCE)
        normalized = resolve_acceptance_fixed_tab_config(resolved_category)
        return {
            "project_id": project_id,
            "base_project_id": resolved_base_project_id,
            "param_code": resolved_param_code,
            "category": resolved_category,
            "ok": ok,
            "message": message,
            "sections": normalized["sections"],
            "project_review_tabs": normalized["project_review_tabs"],
            "tam_tabs": normalized["tam_tabs"],
            "raw_items": raw_items,
        }
    except Exception as exc:
        return {
            "project_id": project_id,
            "base_project_id": resolved_base_project_id,
            "param_code": resolved_param_code,
            "ok": False,
            "message": str(exc),
            "sections": [],
            "project_review_tabs": [],
            "tam_tabs": [],
            "raw_items": raw_items,
        }
    finally:
        log_api_timing(
            "acceptance_tabs",
            started_at,
            project_id=project_id,
            scene=SCENE_ACCEPTANCE,
            base_project_id=resolved_base_project_id,
            param_code=resolved_param_code,
        )


@app.post("/api/generate")
def api_generate(request: Request) -> dict[str, Any]:
    result = build_project_bundle(root=PROJECT_ROOT, config_path=CONFIG_PATH)
    rules_bundle = parse_rule_bundle(resolve_rule_matrix_path(PROJECT_ROOT, result["config"]))
    enabled_skill_groups = set(result["config"].get("generation", {}).get("enabled_skill_groups", []))
    skill_result = generate_approval_item_skills(
        rules_bundle,
        output_dir=INITIATION_SKILLS_DIR,
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


@app.post("/api/integration/check-llm")
def api_check_llm(request: Request) -> dict[str, Any]:
    started_at = time.time()
    try:
        settings = load_llm_settings()
        result = chat_json(
            [
                {"role": "system", "content": "You are a health-check assistant. Return JSON only."},
                {"role": "user", "content": 'Return {"status":"ok","service":"llm"} as JSON.'},
            ],
            temperature=0,
        )
        payload = result.get("json")
        if not isinstance(payload, dict):
            raise ValueError("LLM response is not a JSON object.")
        status = str(payload.get("status") or "").strip().lower()
        ok = status == "ok"
        latency_ms = int((time.time() - started_at) * 1000)
        return {
            "ok": ok,
            "message": "LLM is available." if ok else "LLM returned unexpected status.",
            "model": settings.get("model"),
            "base_url": settings.get("base_url"),
            "latency_ms": latency_ms,
            "used_response_format": bool(result.get("used_response_format")),
            "response": payload,
        }
    except LLMConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if is_llm_unavailable_error(exc):
            raise HTTPException(status_code=502, detail=f"LLM is unavailable: {exc}") from exc
        raise to_http_error(exc) from exc


@app.get("/api/projects")
def api_projects(
    scene: str = SCENE_INITIATION,
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    keyword: str = "",
    project_name: str = "",
    project_code: str = "",
    task_order_no: str = "",
    task_order_name: str = "",
    supplier: str = "",
    domain: str = "",
    department: str = "",
    project_manager: str = "",
    project_type: str = "",
    project_category: str = "",
    fixed_project: str = "",
    project_status: str = "",
    flow_status: str = "",
    task_order_status: str = "",
) -> dict[str, Any]:
    try:
        normalized_scene = normalize_list_scene(scene)
        client = IworkProjectClient(load_integration_config())
        if normalized_scene == SCENE_TASK_ORDER:
            normalized_filters = {
                "task_order_no": task_order_no.strip() or project_code.strip(),
                "task_order_name": task_order_name.strip() or keyword.strip(),
                "supplier": supplier.strip(),
                "project_name": project_name.strip(),
                "domain": domain.strip(),
                "task_order_status": task_order_status.strip() or project_status.strip(),
            }
            remote_filters = {
                "taskNo": normalized_filters["task_order_no"],
                "taskName": normalized_filters["task_order_name"],
                "supplierName": normalized_filters["supplier"],
                "projectName": normalized_filters["project_name"],
                "domainName": normalized_filters["domain"],
                "taskStatus": normalized_filters["task_order_status"],
            }
            remote_filters = {key: value for key, value in remote_filters.items() if value}
            result = client.list_task_orders(
                page_num=page_num,
                page_size=page_size,
                filters=remote_filters or None,
            )
            filtered_projects = [item for item in result["projects"] if matches_task_order_filters(item, normalized_filters)]
        else:
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
                scene=normalized_scene,
                page_num=page_num,
                page_size=page_size,
                filters=remote_filters or None,
            )
            filtered_projects = [item for item in result["projects"] if matches_project_filters(item, normalized_filters)]
        result["projects"] = filtered_projects
        result["filtered_total"] = len(filtered_projects)
        result["filters"] = normalized_filters
        result["scene"] = normalized_scene
        return result
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/project-status-options")
def api_project_status_options(scene: str = SCENE_INITIATION) -> dict[str, Any]:
    try:
        client = IworkProjectClient(load_integration_config())
        normalized_scene = normalize_list_scene(scene)
        if normalized_scene == SCENE_TASK_ORDER:
            return {"items": client.safe_list_task_order_status_options(), "scene": normalized_scene}
        if normalized_scene == SCENE_ACCEPTANCE:
            items = client.safe_list_project_params(ACCEPTANCE_FILTER_QUERY_TYPES["project_status"])
        else:
            items = client.list_project_statuses()
        return {"items": items, "scene": normalized_scene}
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.get("/api/project-filter-options")
def api_project_filter_options(scene: str = SCENE_INITIATION) -> dict[str, Any]:
    try:
        client = IworkProjectClient(load_integration_config())
        normalized_scene = normalize_list_scene(scene)
        if normalized_scene == SCENE_TASK_ORDER:
            try:
                task_order_status_items = client.safe_list_task_order_status_options()
            except Exception:
                task_order_status_items = []
            try:
                supplier_items = client.list_suppliers()
            except Exception:
                supplier_items = []
            return {
                "scene": normalized_scene,
                "items": {
                    "domain": [],
                    "project_category": [],
                    "project_type": [],
                    "project_status": task_order_status_items,
                    "task_order_status": task_order_status_items,
                    "supplier": supplier_items,
                },
            }
        if normalized_scene != SCENE_ACCEPTANCE:
            return {
                "scene": normalized_scene,
                "items": {
                    "project_status": client.list_project_statuses(),
                },
            }
        return {
            "scene": normalized_scene,
            "items": {
                "domain": client.safe_list_project_params(ACCEPTANCE_FILTER_QUERY_TYPES["domain"]),
                "project_category": client.safe_list_project_params(ACCEPTANCE_FILTER_QUERY_TYPES["project_category"]),
                "project_type": [],
                "project_status": client.safe_list_project_params(ACCEPTANCE_FILTER_QUERY_TYPES["project_status"]),
                "task_order_status": [],
            },
        }
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
def api_project_snapshot(
    project_id: str,
    request: Request,
    scene: str = SCENE_INITIATION,
    refresh: bool = False,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    snapshot_payload: dict[str, Any] | None = None
    try:
        client = IworkProjectClient(load_integration_config())
        snapshot_payload = client.fetch_project_snapshot(
            project_id,
            scene=normalize_scene(scene),
            force_refresh=refresh,
            category=str(request.query_params.get("category") or ""),
        )
        return snapshot_payload
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        normalized_scene = normalize_scene(scene)
        log_api_timing(
            "project_snapshot",
            started_at,
            project_id=project_id,
            scene=normalized_scene,
            refresh=refresh,
            **acceptance_id_fields(snapshot_payload if normalized_scene == SCENE_ACCEPTANCE else None),
        )


@app.get("/api/projects/{project_id}/acceptance-info-list")
def api_project_acceptance_info_list(project_id: str) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        client = IworkProjectClient(load_integration_config())
        items = client.fetch_acceptance_info_list(project_id)
        return {"project_id": project_id, "items": items}
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        log_api_timing("project_acceptance_info_list", started_at, project_id=project_id)


@app.get("/api/projects/{project_id}/task-orders")
def api_project_task_orders(project_id: str) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        client = IworkProjectClient(load_integration_config())
        items = client.list_task_orders_by_project(project_id)
        return {"project_id": project_id, "items": items, "scene": SCENE_TASK_ORDER}
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        log_api_timing("project_task_orders", started_at, project_id=project_id, scene=SCENE_TASK_ORDER)


@app.get("/api/review-projects")
def api_review_projects(scene: str = SCENE_ACCEPTANCE) -> dict[str, Any]:
    started_at = time.perf_counter()
    normalized_scene = normalize_list_scene(scene)
    try:
        client = IworkProjectClient(load_integration_config())
        if normalized_scene == SCENE_ACCEPTANCE:
            return client.list_acceptance_review_projects(status_codes=["4", "9"])
        result = client.list_projects(scene=normalized_scene, page_num=1, page_size=100)
        result["scene"] = normalized_scene
        return result
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        log_api_timing("review_projects", started_at, scene=normalized_scene)


@app.get("/api/task-orders/{task_order_id}/detail")
def api_task_order_detail(task_order_id: str, project_id: str = "") -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        client = IworkProjectClient(load_integration_config())
        result = client.fetch_task_order_detail(task_order_id=task_order_id, project_id=project_id)
        return result
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        log_api_timing(
            "task_order_detail",
            started_at,
            project_id=project_id or "-",
            scene=SCENE_TASK_ORDER,
            task_order_id=task_order_id,
        )


@app.get("/api/contracts/{contract_id}/detail")
def api_contract_detail(contract_id: str, contract_number: str = "") -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        client = IworkProjectClient(load_integration_config())
        return client.fetch_contract_detail(contract_id=contract_id, contract_number=contract_number)
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        log_api_timing(
            "contract_detail",
            started_at,
            project_id=contract_id or contract_number or "-",
            scene=SCENE_ACCEPTANCE,
        )


@app.get("/api/projects/{project_id}/document")
def api_project_document(
    project_id: str,
    category: str = DEFAULT_PROJECT_CATEGORY,
    scene: str = SCENE_INITIATION,
    refresh: bool = False,
    include_architecture_reviews: bool = True,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    document_payload: dict[str, Any] | None = None
    try:
        normalized_scene = normalize_scene(scene)
        client = IworkProjectClient(load_integration_config())
        requested_category = str(category or "").strip()
        summary = load_cached_project_summary(project_id, scene=normalized_scene) or {}
        resolved_category = resolve_project_category_name(requested_category, summary=summary, scene=normalized_scene)
        document, _, _ = build_project_document(
            client=client,
            project_id=project_id,
            category=resolved_category,
            scene=normalized_scene,
            refresh=refresh,
            include_architecture_reviews=include_architecture_reviews,
        )
        document_payload = document
        document["requested_category"] = requested_category or resolved_category
        document["resolved_category"] = resolve_project_category_name(
            requested_category,
            summary=summary,
            document=document,
            scene=normalized_scene,
        )
        document["scene"] = normalized_scene
        return document
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        normalized_scene = normalize_scene(scene)
        log_api_timing(
            "project_document",
            started_at,
            project_id=project_id,
            scene=normalized_scene,
            refresh=refresh,
            include_architecture_reviews=include_architecture_reviews,
            **acceptance_id_fields((document_payload or {}).get("debug_ids") if normalized_scene == SCENE_ACCEPTANCE else None),
        )


@app.get("/api/projects/{project_id}/architecture-reviews")
def api_project_architecture_reviews(
    project_id: str,
    category: str = DEFAULT_PROJECT_CATEGORY,
    scene: str = SCENE_INITIATION,
    refresh: bool = False,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    review_payload: dict[str, Any] | None = None
    try:
        normalized_scene = normalize_scene(scene)
        client = IworkProjectClient(load_integration_config())
        requested_category = str(category or "").strip()
        summary = load_cached_project_summary(project_id, scene=normalized_scene) or {}
        resolved_category = resolve_project_category_name(requested_category, summary=summary, scene=normalized_scene)
        review_payload = build_architecture_review_payload(
            client=client,
            project_id=project_id,
            category=resolved_category,
            scene=normalized_scene,
            refresh=refresh,
        )
        return review_payload
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        normalized_scene = normalize_scene(scene)
        log_api_timing(
            "project_architecture_reviews",
            started_at,
            project_id=project_id,
            scene=normalized_scene,
            refresh=refresh,
            **acceptance_id_fields((review_payload or {}).get("debug_ids") if normalized_scene == SCENE_ACCEPTANCE else None),
        )


@app.get("/api/projects/{project_id}/latest-approval")
def api_project_latest_approval(
    project_id: str,
    category: str = DEFAULT_PROJECT_CATEGORY,
    scene: str = SCENE_INITIATION,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    debug_id_payload: dict[str, Any] | None = None
    try:
        normalized_scene = normalize_scene(scene)
        if normalized_scene == SCENE_ACCEPTANCE:
            client = IworkProjectClient(load_integration_config())
            debug_id_payload = client.resolve_acceptance_project_ids(project_id)
        requested_category = str(category or "").strip()
        summary = load_cached_project_summary(project_id, scene=normalized_scene) or {}
        resolved_category = resolve_project_category_name(requested_category, summary=summary, scene=normalized_scene)
        result = load_latest_remote_approval_result(
            project_id=project_id,
            category=resolved_category,
            scene=normalized_scene,
        )
        return {
            "found": result is not None,
            "requested_category": requested_category or resolved_category,
            "resolved_category": resolved_category,
            "scene": normalized_scene,
            "result": result,
        }
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        normalized_scene = normalize_scene(scene)
        log_api_timing(
            "project_latest_approval",
            started_at,
            project_id=project_id,
            scene=normalized_scene,
            **acceptance_id_fields(debug_id_payload if normalized_scene == SCENE_ACCEPTANCE else None),
        )


@app.get("/api/projects/{project_id}/approval-compare")
def api_project_approval_compare(
    project_id: str,
    category: str = DEFAULT_PROJECT_CATEGORY,
    scene: str = SCENE_ACCEPTANCE,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    debug_id_payload: dict[str, Any] | None = None
    try:
        normalized_scene = normalize_scene(scene)
        budget_project_id = str(project_id or "").strip()
        initiation_project_id = budget_project_id
        if normalized_scene == SCENE_ACCEPTANCE:
            client = IworkProjectClient(load_integration_config())
            debug_id_payload = client.resolve_acceptance_project_ids(project_id)
            budget_project_id = str(debug_id_payload.get("budget_project_id") or project_id).strip() or str(project_id)
            initiation_project_id = str(debug_id_payload.get("establishment_project_id") or budget_project_id).strip() or budget_project_id

        requested_category = str(category or "").strip()
        acceptance_summary = load_cached_project_summary(budget_project_id, scene=SCENE_ACCEPTANCE) or {}
        initiation_summary = load_cached_project_summary(initiation_project_id, scene=SCENE_INITIATION) or {}
        acceptance_category = resolve_project_category_name(requested_category, summary=acceptance_summary, scene=SCENE_ACCEPTANCE)
        initiation_category = resolve_project_category_name(requested_category, summary=initiation_summary, scene=SCENE_INITIATION)

        acceptance_result = load_latest_remote_approval_result(
            project_id=budget_project_id,
            category=acceptance_category,
            scene=SCENE_ACCEPTANCE,
        ) or load_latest_remote_approval_result_any_category(
            project_id=budget_project_id,
            scene=SCENE_ACCEPTANCE,
        )
        initiation_result = load_latest_remote_approval_result(
            project_id=initiation_project_id,
            category=initiation_category,
            scene=SCENE_INITIATION,
        ) or load_latest_remote_approval_result_any_category(
            project_id=initiation_project_id,
            scene=SCENE_INITIATION,
        )

        return {
            "project_id": budget_project_id,
            "scene": normalized_scene,
            "requested_category": requested_category or acceptance_category,
            "budget_project_id": budget_project_id,
            "initiation_project_id": initiation_project_id,
            "acceptance": {
                "found": acceptance_result is not None,
                "resolved_category": acceptance_category,
                "result": acceptance_result,
            },
            "initiation": {
                "found": initiation_result is not None,
                "resolved_category": initiation_category,
                "result": initiation_result,
            },
        }
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        log_api_timing(
            "project_approval_compare",
            started_at,
            project_id=project_id,
            scene=normalize_scene(scene),
            **acceptance_id_fields(debug_id_payload if normalize_scene(scene) == SCENE_ACCEPTANCE else None),
        )


@app.get("/api/review-feedback")
def api_review_feedback(
    category: str = DEFAULT_PROJECT_CATEGORY,
    scene: str = SCENE_INITIATION,
) -> dict[str, Any]:
    try:
        normalized_scene = normalize_scene(scene)
        cached_payload = _load_cached_review_feedback(category, normalized_scene)
        if cached_payload is not None:
            return cached_payload
        review_items = load_latest_review_feedback_map(category, scene=normalized_scene)
        approval_items = load_latest_remote_approval_result_map(category, scene=normalized_scene)
        payload = {
            "scene": normalized_scene,
            "items": merge_review_feedback_with_approvals(review_items, approval_items),
        }
        _store_cached_review_feedback(category, payload, normalized_scene)
        return payload
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.post("/api/review-feedback")
def api_save_review_feedback(payload: dict[str, Any], scene: str = SCENE_INITIATION) -> dict[str, Any]:
    project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="Missing projectId.")

    normalized_scene = normalize_scene(payload.get("scene") or scene)
    category = str(payload.get("category") or DEFAULT_PROJECT_CATEGORY).strip() or DEFAULT_PROJECT_CATEGORY
    project_name = str(payload.get("projectName") or payload.get("project_name") or project_id).strip() or project_id
    feedback = payload.get("feedback")
    if not isinstance(feedback, dict):
        raise HTTPException(status_code=400, detail="Missing feedback payload.")

    try:
        saved_record = persist_review_feedback(
            project_id=project_id,
            project_name=project_name,
            category=category,
            scene=normalized_scene,
            feedback=feedback,
        )
        _invalidate_review_feedback_cache(category, normalized_scene)
        return saved_record
    except Exception as exc:
        raise to_http_error(exc) from exc


@app.post("/api/approve")
def api_approve(payload: dict[str, Any]) -> dict[str, Any]:
    category = payload.get("category")
    scene = normalize_scene(payload.get("scene"))
    document = payload.get("document", payload)
    return evaluate_approval(document=document, category=category, scene=scene)


@app.post("/api/approve/llm")
def api_approve_llm(payload: dict[str, Any]) -> dict[str, Any]:
    project_name = payload.get("project_name") or payload.get("projectName") or "unnamed-project"
    project_id = payload.get("project_id") or payload.get("projectId") or project_name
    category = payload.get("category", DEFAULT_PROJECT_CATEGORY)
    scene = normalize_scene(payload.get("scene"))
    snapshot = payload.get("snapshot") or {"project_id": project_id, "endpoints": {}}
    document = payload.get("document") or payload
    try:
        result = run_llm_approval(
            project_name=project_name,
            project_id=project_id,
            category=category,
            scene=scene,
            snapshot=snapshot,
            document=document,
        )
        _invalidate_review_feedback_cache(str(category), scene)
        return result
    except Exception as exc:
        if is_llm_unavailable_error(exc):
            return build_deterministic_approval_fallback(
                project_name=str(project_name),
                project_id=str(project_id),
                category=str(category),
                scene=scene,
                document=document,
                reason=str(exc),
            )
        raise to_http_error(exc) from exc


@app.post("/api/approve/generated-project")
def api_approve_generated_project(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = payload or {}
    scene = normalize_scene(request_payload.get("scene"))
    category = resolve_project_category_name(request_payload.get("category"), scene=scene)
    document = normalize_generated_bundle(load_generated_project_bundle(), category)
    return evaluate_approval(document=document, category=category, scene=scene)


@app.post("/api/approve/remote-project")
def api_approve_remote_project(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload["projectId"] or "").strip()
    task_order_id = str(payload.get("taskOrderId") or payload.get("task_order_id") or "").strip()
    scene = normalize_scene(payload.get("scene"))
    requested_category = str(payload.get("category") or "").strip()
    refresh_document = bool(payload.get("refreshDocument") or payload.get("refresh_document"))
    started_at = time.perf_counter()
    debug_id_payload: dict[str, Any] | None = None
    try:
        client = IworkProjectClient(load_integration_config())
        document_project_id = project_id
        approval_result_project_id = project_id
        if scene == SCENE_TASK_ORDER and task_order_id:
            approval_result_project_id = task_order_id

        if scene == SCENE_ACCEPTANCE:
            debug_id_payload = client.resolve_acceptance_project_ids(project_id)
        summary = load_cached_project_summary(document_project_id, scene=scene) or {}
        category = resolve_project_category_name(requested_category, summary=summary, scene=scene)
        document, snapshot, _ = build_project_document(
            client=client,
            project_id=document_project_id,
            category=category,
            scene=scene,
            refresh=refresh_document,
        )
        if scene == SCENE_ACCEPTANCE:
            document_summary = document.get("project_summary") if isinstance(document.get("project_summary"), dict) else {}
            resolved_from_document = resolve_project_category_name(
                None,
                summary=document_summary,
                document=document,
                scene=scene,
            )
            if resolved_from_document and resolved_from_document != category:
                category = resolved_from_document
                document, snapshot, _ = build_project_document(
                    client=client,
                    project_id=document_project_id,
                    category=category,
                    scene=scene,
                    refresh=refresh_document,
                )
        category = resolve_project_category_name(None if scene == SCENE_ACCEPTANCE else requested_category, summary=summary, document=document, scene=scene)
        approval_project_name = str(document.get("project_name") or document_project_id)
        try:
            result = run_llm_approval(
                project_name=approval_project_name,
                project_id=approval_result_project_id,
                category=category,
                scene=scene,
                snapshot=snapshot,
                document=document,
            )
        except Exception as exc:
            if not is_llm_unavailable_error(exc):
                raise
            result = build_deterministic_approval_fallback(
                project_name=approval_project_name,
                project_id=approval_result_project_id,
                category=category,
                scene=scene,
                document=document,
                reason=str(exc),
            )
        result["requested_category"] = requested_category or category
        result["resolved_category"] = category
        result["scene"] = scene
        _invalidate_review_feedback_cache(str(category), scene)
        return result
    except Exception as exc:
        raise to_http_error(exc) from exc
    finally:
        log_api_timing(
            "approve_remote_project",
            started_at,
            project_id=project_id,
            scene=scene,
            task_order_id=task_order_id,
            refresh_document=refresh_document,
            **acceptance_id_fields(debug_id_payload if scene == SCENE_ACCEPTANCE else None),
        )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
