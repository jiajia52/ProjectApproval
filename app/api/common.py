from __future__ import annotations

from typing import Any

from app.approvals.engine.approval_results import (
    load_latest_remote_approval_result as _load_latest_remote_approval_result,
    load_latest_remote_approval_result_any_category as _load_latest_remote_approval_result_any_category,
    load_latest_remote_approval_result_map as _load_latest_remote_approval_result_map,
)
from app.approvals.review.acceptance_tabs import resolve_acceptance_fixed_tab_config as _resolve_acceptance_fixed_tab_config
from app.core.support.category_resolution import resolve_project_category_name as _resolve_project_category_name

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


def resolve_acceptance_fixed_tab_config(category: Any) -> dict[str, list[str]]:
    return _resolve_acceptance_fixed_tab_config(
        category,
        default_project_category=DEFAULT_PROJECT_CATEGORY,
    )


def resolve_project_category_name(
    requested_category: str | None = None,
    summary: dict[str, Any] | None = None,
    document: dict[str, Any] | None = None,
    scene: str = SCENE_INITIATION,
) -> str:
    return _resolve_project_category_name(
        requested_category=requested_category,
        summary=summary,
        document=document,
        scene=scene,
        default_project_category=DEFAULT_PROJECT_CATEGORY,
    )


def load_latest_remote_approval_result(
    project_id: str,
    category: str,
    scene: str = SCENE_INITIATION,
) -> dict[str, Any] | None:
    return _load_latest_remote_approval_result(
        project_id,
        category,
        scene=scene,
        default_project_category=DEFAULT_PROJECT_CATEGORY,
    )


def load_latest_remote_approval_result_any_category(
    project_id: str,
    scene: str = SCENE_INITIATION,
) -> dict[str, Any] | None:
    return _load_latest_remote_approval_result_any_category(project_id, scene=scene)


def load_latest_remote_approval_result_map(
    category: str,
    scene: str = SCENE_INITIATION,
) -> dict[str, dict[str, Any]]:
    return _load_latest_remote_approval_result_map(
        category,
        scene=scene,
        default_project_category=DEFAULT_PROJECT_CATEGORY,
    )
