from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from app.approvals.clients.iwork_client import (
    IworkProjectClient,
    load_cached_project_snapshot,
    load_cached_project_summary,
)
from app.approvals.document.project_document_store import load_project_document, persist_project_document
from app.approvals.document.remote_project_mapper import map_snapshot_to_document
from app.approvals.document.snapshot_utils import merge_project_snapshots, snapshot_has_usable_data
from app.approvals.engine.approval_results import stale_acceptance_persisted_document as _stale_acceptance_persisted_document
from app.approvals.review.architecture_review_utils import (
    architecture_review_groups_have_material as _architecture_review_groups_have_material,
    review_groups_to_document_fields,
)
from app.approvals.review.architecture_reviews import (
    build_architecture_review_groups_from_snapshot as _build_architecture_review_groups_from_snapshot,
    collect_acceptance_architecture_review_groups,
    collect_architecture_review_groups,
)
from app.core.cache.transient_cache import (
    load_cached_architecture_reviews as _load_cached_architecture_reviews,
    store_cached_architecture_reviews as _store_cached_architecture_reviews,
)
from app.core.config.scenes import normalize_scene
from app.core.support.main_helpers import acceptance_id_fields, log_api_timing

SCENE_INITIATION = "initiation"
SCENE_ACCEPTANCE = "acceptance"


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
