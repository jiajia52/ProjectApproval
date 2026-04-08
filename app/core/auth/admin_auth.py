from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request

ADMIN_SESSION_COOKIE = "project_approval_admin_session"
ADMIN_SESSION_MAX_AGE = 8 * 60 * 60


def get_management_credentials() -> tuple[str, str]:
    username = os.getenv("PROJECT_APPROVAL_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("PROJECT_APPROVAL_ADMIN_PASSWORD", "admin123")
    return username, password


def ensure_admin_sessions(app_instance: FastAPI) -> dict[str, dict[str, Any]]:
    sessions = getattr(app_instance.state, "admin_sessions", None)
    if not isinstance(sessions, dict):
        sessions = {}
        app_instance.state.admin_sessions = sessions
    return sessions


def get_admin_session(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "").strip()
    if not token:
        return None
    return ensure_admin_sessions(request.app).get(token)


def require_management_auth(request: Request) -> dict[str, Any]:
    session = get_admin_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="需要先登录管理界面。")
    return session


def new_admin_session(username: str) -> dict[str, Any]:
    return {
        "username": username,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
