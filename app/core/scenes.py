from __future__ import annotations

SCENE_INITIATION = "initiation"
SCENE_ACCEPTANCE = "acceptance"
SCENE_TASK_ORDER = "task_order"


def normalize_scene(scene: str | None) -> str:
    normalized = str(scene or "").strip().lower()
    if normalized in {SCENE_TASK_ORDER, "task-order", "taskorder"}:
        return SCENE_TASK_ORDER
    return SCENE_ACCEPTANCE if normalized == SCENE_ACCEPTANCE else SCENE_INITIATION
