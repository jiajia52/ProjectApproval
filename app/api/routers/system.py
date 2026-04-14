from __future__ import annotations

import json
import sys
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.approvals.clients.iwork_client import IworkProjectClient, load_integration_config, save_integration_config
from app.approvals.engine.approval_engine import load_or_create_sample_document
from app.core.config.paths import CONFIG_PATH, INITIATION_SKILLS_DIR, PROJECT_ROOT, SCRIPTS_DIR
from app.core.llm.llm_client import LLMConfigError, chat_json, load_llm_settings
from app.core.runtime.runtime_artifacts import ensure_runtime_artifacts, ensure_scene_artifacts
from app.core.runtime.startup_state import refresh_startup_checks
from app.core.support.main_helpers import list_outputs, normalize_skill_scene
from app.core.web.http_errors import is_llm_unavailable_error, to_http_error
from app.skills.manager import get_skill_manager

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_project_approval_bundle import build_project_bundle, resolve_rule_matrix_path  # noqa: E402
from extract_review_rules import parse_rule_bundle  # noqa: E402
from generate_approval_item_skills import generate_approval_item_skills  # noqa: E402

router = APIRouter()
SCENE_INITIATION = "initiation"


@router.get("/api/config")
def api_config(request: Request) -> dict[str, Any]:
    config, _ = ensure_runtime_artifacts(force=False)
    return config


@router.put("/api/config")
def api_save_config(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _, rules_bundle = ensure_runtime_artifacts(force=True)
    refresh_startup_checks(request.app, rules_bundle=rules_bundle)
    return api_config(request)


@router.get("/api/rules")
def api_rules(request: Request, scene: str = SCENE_INITIATION) -> dict[str, Any]:
    _, rules_bundle = ensure_scene_artifacts(normalize_skill_scene(scene), force=False)
    return rules_bundle


@router.post("/api/generate")
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
    refresh_startup_checks(request.app, rules_bundle=rules_bundle)
    return result


@router.get("/api/outputs")
def api_outputs(request: Request) -> list[dict[str, str]]:
    return list_outputs()


@router.get("/api/approval/sample")
def api_approval_sample() -> dict[str, Any]:
    return load_or_create_sample_document()


@router.get("/api/integration/config")
def api_integration_config(request: Request) -> dict[str, Any]:
    return load_integration_config()


@router.put("/api/integration/config")
def api_save_integration_config(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_integration_config(payload)


@router.post("/api/integration/refresh-token")
def api_refresh_integration_token(request: Request) -> dict[str, Any]:
    client = IworkProjectClient(load_integration_config())
    try:
        token = client.refresh_token()
    except Exception as exc:
        raise to_http_error(exc) from exc
    return {"token": token, "config": load_integration_config()}


@router.post("/api/integration/check-llm")
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


@router.get("/api/discovery/nacos/instances")
def api_nacos_instances(
    request: Request,
    service_name: str = "",
    healthy_only: bool = True,
    group_name: str = "",
) -> dict[str, Any]:
    client = getattr(request.app.state, "nacos_discovery", None)
    if client is None:
        raise HTTPException(status_code=400, detail="Nacos discovery is not enabled.")
    resolved_service_name = str(service_name or "").strip() or str(getattr(client, "service_name", "") or "").strip()
    resolved_group = str(group_name or "").strip() or str(getattr(client, "group_name", "DEFAULT_GROUP") or "DEFAULT_GROUP")
    if not resolved_service_name:
        raise HTTPException(status_code=400, detail="service_name is required.")
    try:
        instances = client.list_instances(
            resolved_service_name,
            healthy_only=healthy_only,
            group_name=resolved_group,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc
    return {
        "service_name": resolved_service_name,
        "group_name": resolved_group,
        "healthy_only": healthy_only,
        "count": len(instances),
        "instances": instances,
    }


@router.get("/api/discovery/nacos/pick")
def api_nacos_pick_instance(
    request: Request,
    service_name: str = "",
    healthy_only: bool = True,
    group_name: str = "",
) -> dict[str, Any]:
    client = getattr(request.app.state, "nacos_discovery", None)
    if client is None:
        raise HTTPException(status_code=400, detail="Nacos discovery is not enabled.")
    resolved_service_name = str(service_name or "").strip() or str(getattr(client, "service_name", "") or "").strip()
    resolved_group = str(group_name or "").strip() or str(getattr(client, "group_name", "DEFAULT_GROUP") or "DEFAULT_GROUP")
    if not resolved_service_name:
        raise HTTPException(status_code=400, detail="service_name is required.")
    try:
        selected = client.choose_instance(
            resolved_service_name,
            healthy_only=healthy_only,
            group_name=resolved_group,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc
    return {
        "service_name": resolved_service_name,
        "group_name": resolved_group,
        "healthy_only": healthy_only,
        "instance": selected,
    }
