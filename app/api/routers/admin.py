from __future__ import annotations

import hmac
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.auth.admin_auth import (
    ADMIN_SESSION_COOKIE,
    ADMIN_SESSION_MAX_AGE,
    ensure_admin_sessions,
    get_admin_session,
    get_management_credentials,
    new_admin_session,
)
from app.core.runtime.runtime_artifacts import ensure_runtime_artifacts
from app.core.runtime.startup_state import refresh_startup_checks

router = APIRouter()


@router.get("/api/admin/session")
def api_admin_session(request: Request) -> dict[str, Any]:
    session = get_admin_session(request)
    if session is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "username": session.get("username") or get_management_credentials()[0],
    }


@router.post("/api/admin/login")
def api_admin_login(payload: dict[str, Any], request: Request) -> JSONResponse:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    expected_username, expected_password = get_management_credentials()
    if not (
        hmac.compare_digest(username, expected_username)
        and hmac.compare_digest(password, expected_password)
    ):
        raise HTTPException(status_code=401, detail="账号或密码错误。")

    session_token = secrets.token_urlsafe(32)
    ensure_admin_sessions(request.app)[session_token] = new_admin_session(expected_username)
    response = JSONResponse({"authenticated": True, "username": expected_username})
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=session_token,
        max_age=ADMIN_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/api/admin/logout")
def api_admin_logout(request: Request) -> JSONResponse:
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "").strip()
    if token:
        ensure_admin_sessions(request.app).pop(token, None)
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(ADMIN_SESSION_COOKIE, samesite="lax")
    return response


@router.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    startup_checks = getattr(request.app.state, "startup_checks", None)
    if startup_checks is None:
        _, rules_bundle = ensure_runtime_artifacts(force=False)
        startup_checks = refresh_startup_checks(request.app, rules_bundle=rules_bundle)
    return {
        "status": startup_checks["overall_status"],
        "summary": startup_checks["summary"],
        "generated_at": startup_checks["generated_at"],
    }


@router.get("/api/startup-checks")
def api_startup_checks(request: Request) -> dict[str, Any]:
    startup_checks = getattr(request.app.state, "startup_checks", None)
    if startup_checks is None:
        _, rules_bundle = ensure_runtime_artifacts(force=False)
        startup_checks = refresh_startup_checks(request.app, rules_bundle=rules_bundle)
    return startup_checks
