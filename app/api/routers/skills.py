from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.core.runtime.runtime_artifacts import ensure_scene_artifacts
from app.core.support.main_helpers import normalize_skill_scene
from app.skills.manager import get_skill_manager

router = APIRouter()
SCENE_INITIATION = "initiation"


@router.get("/api/skills")
def api_skills(request: Request, scene: str = SCENE_INITIATION) -> list[dict[str, Any]]:
    normalized_scene = normalize_skill_scene(scene)
    ensure_scene_artifacts(normalized_scene, force=False)
    return get_skill_manager(normalized_scene).list_skills()


@router.get("/api/skill-files")
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


@router.get("/api/skill-files/{skill_id}")
def api_skill_file(skill_id: str, request: Request, scene: str = SCENE_INITIATION) -> dict[str, Any]:
    normalized_scene = normalize_skill_scene(scene)
    ensure_scene_artifacts(normalized_scene, force=False)
    manager = get_skill_manager(normalized_scene)
    try:
        return manager.read_skill_file(skill_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/skill-files/{skill_id}")
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
