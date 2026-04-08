from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.approvals.clients.iwork_client import IworkProjectClient, build_project_snapshot_requests, load_integration_config
from app.approvals.engine.approval_engine import evaluate_approval, load_or_create_sample_document
from app.core.config.paths import (
    CONFIG_PATH,
    PROJECT_ROOT,
    RULES_BUNDLE_PATH,
    SCRIPTS_DIR,
    SKILL_MANIFEST_PATH,
    STARTUP_CHECKS_PATH,
    find_rule_matrix_path,
)
from app.core.llm.llm_client import LLMConfigError, load_llm_settings
from app.skills.manager import get_skill_manager

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from extract_review_rules import parse_rule_bundle  # noqa: E402


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_check(
    name: str,
    *,
    status: str,
    required: bool,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "required": required,
        "message": message,
        "details": details or {},
    }


def check_rule_matrix(rules_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        matrix_path = find_rule_matrix_path()
        bundle = rules_bundle or parse_rule_bundle(matrix_path)
        return build_check(
            "data_extraction",
            status="ok",
            required=True,
            message="Rule matrix parsed successfully.",
            details={
                "source": str(matrix_path),
                "rule_count": bundle.get("summary", {}).get("rule_count", 0),
                "review_point_count": len(bundle.get("summary", {}).get("by_review_point", {})),
            },
        )
    except Exception as exc:
        return build_check(
            "data_extraction",
            status="error",
            required=True,
            message=str(exc),
        )


def check_runtime_outputs() -> dict[str, Any]:
    missing: list[str] = []
    for path in [CONFIG_PATH, RULES_BUNDLE_PATH, SKILL_MANIFEST_PATH]:
        if not path.exists():
            missing.append(str(path))
    if missing:
        return build_check(
            "runtime_outputs",
            status="error",
            required=True,
            message="Required runtime artifacts are missing.",
            details={"missing": missing},
        )
    return build_check(
        "runtime_outputs",
        status="ok",
        required=True,
        message="Runtime artifacts are present.",
        details={
            "config_path": str(CONFIG_PATH),
            "rules_bundle_path": str(RULES_BUNDLE_PATH),
            "skill_manifest_path": str(SKILL_MANIFEST_PATH),
        },
    )


def check_skills() -> dict[str, Any]:
    try:
        manager = get_skill_manager()
        manager.initialize()
        skills = manager.list_skills()
        if not skills:
            return build_check(
                "skills",
                status="error",
                required=True,
                message="No approval skills were loaded.",
            )
        return build_check(
            "skills",
            status="ok",
            required=True,
            message="Approval skills loaded successfully.",
            details={
                "skill_count": len(skills),
                "sample_skills": [item.get("name", "") for item in skills[:5]],
            },
        )
    except Exception as exc:
        return build_check(
            "skills",
            status="error",
            required=True,
            message=str(exc),
        )


def check_approval_engine() -> dict[str, Any]:
    try:
        document = load_or_create_sample_document()
        result = evaluate_approval(document=document, category=document.get("category"))
        return build_check(
            "approval_engine",
            status="ok",
            required=True,
            message="Approval engine evaluated the sample document successfully.",
            details={
                "decision": result.get("decision", ""),
                "score": result.get("score", 0),
                "total_rules": result.get("statistics", {}).get("total_rules", 0),
            },
        )
    except Exception as exc:
        return build_check(
            "approval_engine",
            status="error",
            required=True,
            message=str(exc),
        )


def check_remote_data_module() -> dict[str, Any]:
    try:
        config = load_integration_config()
        client = IworkProjectClient(config)
        endpoints = build_project_snapshot_requests("startup-check")
        has_token = bool(str(config.get("token", "")).strip())
        has_iam = bool(str(config.get("iam_full_url", "")).strip() or str(config.get("iam_code", "")).strip())
        verify_ssl = bool(config.get("verify_ssl", True))
        ca_bundle_path = str(config.get("ca_bundle_path", "") or "").strip()
        tls_mode = "disabled" if not verify_ssl else "custom_ca_bundle" if ca_bundle_path else "requests_default_ca_bundle"
        status = "ok" if has_token or has_iam else "warning"
        message = (
            "Remote data extraction is configured."
            if status == "ok"
            else "Remote data extraction module is available, but token/IAM config is missing."
        )
        if not verify_ssl:
            message = f"{message} TLS certificate verification is disabled."
        return build_check(
            "remote_data",
            status=status,
            required=False,
            message=message,
            details={
                "base_url": client.base_url,
                "endpoint_count": len(endpoints),
                "has_token": has_token,
                "use_iam": bool(config.get("use_iam")),
                "has_iam_callback": has_iam,
                "verify_ssl": verify_ssl,
                "ca_bundle_path": ca_bundle_path,
                "tls_mode": tls_mode,
            },
        )
    except Exception as exc:
        return build_check(
            "remote_data",
            status="warning",
            required=False,
            message=str(exc),
        )


def check_llm_module() -> dict[str, Any]:
    try:
        settings = load_llm_settings()
        return build_check(
            "llm",
            status="ok",
            required=False,
            message="LLM configuration is complete.",
            details={
                "base_url": settings["base_url"],
                "model": settings["model"],
                "timeout": settings["timeout"],
                "verify_ssl": settings["verify_ssl"],
            },
        )
    except LLMConfigError as exc:
        return build_check(
            "llm",
            status="warning",
            required=False,
            message=str(exc),
        )
    except Exception as exc:
        return build_check(
            "llm",
            status="warning",
            required=False,
            message=str(exc),
        )


def summarize_checks(checks: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    summary = {"ok": 0, "warning": 0, "error": 0}
    for item in checks:
        status = item["status"]
        summary[status] = summary.get(status, 0) + 1
    if any(item["required"] and item["status"] == "error" for item in checks):
        overall_status = "error"
    elif summary["warning"] or summary["error"]:
        overall_status = "warning"
    else:
        overall_status = "ok"
    return overall_status, summary


def run_startup_checks(*, rules_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    checks = [
        check_rule_matrix(rules_bundle),
        check_runtime_outputs(),
        check_skills(),
        check_approval_engine(),
        check_remote_data_module(),
        check_llm_module(),
    ]
    overall_status, summary = summarize_checks(checks)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": overall_status,
        "summary": summary,
        "checks": checks,
    }
    write_json(STARTUP_CHECKS_PATH, payload)
    return payload
