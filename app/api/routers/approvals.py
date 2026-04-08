from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.common import (
    DEFAULT_PROJECT_CATEGORY,
    SCENE_ACCEPTANCE,
    SCENE_INITIATION,
    SCENE_TASK_ORDER,
    load_latest_remote_approval_result_map,
    resolve_project_category_name,
)
from app.approvals.clients.iwork_client import IworkProjectClient, load_cached_project_summary, load_integration_config
from app.approvals.document.project_document_builder import build_project_document
from app.approvals.engine.approval_engine import evaluate_approval, load_generated_project_bundle, normalize_generated_bundle
from app.approvals.engine.approval_results import merge_review_feedback_with_approvals
from app.approvals.engine.deterministic_fallback import build_deterministic_approval_fallback
from app.approvals.engine.llm_approval_service import run_llm_approval
from app.approvals.review.review_feedback_store import load_latest_review_feedback_map, persist_review_feedback
from app.core.cache.transient_cache import (
    invalidate_review_feedback_cache as _invalidate_review_feedback_cache,
    load_cached_review_feedback as _load_cached_review_feedback,
    store_cached_review_feedback as _store_cached_review_feedback,
)
from app.core.config.scenes import normalize_scene
from app.core.support.main_helpers import acceptance_id_fields, log_api_timing
from app.core.web.http_errors import is_llm_unavailable_error, to_http_error

router = APIRouter()


@router.get("/api/review-feedback")
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


@router.post("/api/review-feedback")
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


@router.post("/api/approve")
def api_approve(payload: dict[str, Any]) -> dict[str, Any]:
    category = payload.get("category")
    scene = normalize_scene(payload.get("scene"))
    document = payload.get("document", payload)
    return evaluate_approval(document=document, category=category, scene=scene)


@router.post("/api/approve/llm")
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


@router.post("/api/approve/generated-project")
def api_approve_generated_project(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = payload or {}
    scene = normalize_scene(request_payload.get("scene"))
    category = resolve_project_category_name(request_payload.get("category"), scene=scene)
    document = normalize_generated_bundle(load_generated_project_bundle(), category)
    return evaluate_approval(document=document, category=category, scene=scene)


@router.post("/api/approve/remote-project")
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
