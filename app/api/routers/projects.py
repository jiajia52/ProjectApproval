from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.api.common import (
    ACCEPTANCE_FILTER_QUERY_TYPES,
    DEFAULT_PROJECT_CATEGORY,
    SCENE_ACCEPTANCE,
    SCENE_INITIATION,
    SCENE_TASK_ORDER,
    load_latest_remote_approval_result,
    load_latest_remote_approval_result_any_category,
    resolve_acceptance_fixed_tab_config,
    resolve_project_category_name,
)
from app.approvals.clients.iwork_client import (
    IworkProjectClient,
    first_non_empty,
    load_cached_project_summary,
    load_integration_config,
    matches_project_filters,
    matches_task_order_filters,
)
from app.approvals.document.project_document_builder import (
    build_architecture_review_payload,
    build_project_document,
)
from app.core.config.scenes import normalize_scene
from app.core.support.main_helpers import acceptance_id_fields, log_api_timing, normalize_list_scene
from app.core.web.http_errors import to_http_error

router = APIRouter()


@router.get("/api/projects/{project_id}/acceptance-tabs")
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


@router.get("/api/projects")
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


@router.get("/api/project-status-options")
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


@router.get("/api/project-filter-options")
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


@router.get("/api/files/download")
def api_download_file(path: str = Query(..., min_length=1)) -> Response:
    try:
        client = IworkProjectClient(load_integration_config())
        content, media_type = client.download_file(path)
        return Response(content=content, media_type=media_type)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/api/projects/{project_id}/snapshot")
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


@router.get("/api/projects/{project_id}/acceptance-info-list")
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


@router.get("/api/projects/{project_id}/task-orders")
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


@router.get("/api/review-projects")
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


@router.get("/api/task-orders/{task_order_id}/detail")
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


@router.get("/api/contracts/{contract_id}/detail")
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


@router.get("/api/projects/{project_id}/document")
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


@router.get("/api/projects/{project_id}/architecture-reviews")
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


@router.get("/api/projects/{project_id}/latest-approval")
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


@router.get("/api/projects/{project_id}/approval-compare")
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
