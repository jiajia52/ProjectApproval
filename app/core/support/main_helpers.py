from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from app.core.config.paths import scene_generated_dir
from app.core.config.scenes import normalize_scene

SCENE_INITIATION = "initiation"
SCENE_ACCEPTANCE = "acceptance"
SCENE_TASK_ORDER = "task_order"
LOGGER = logging.getLogger("project_approval.startup")


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
