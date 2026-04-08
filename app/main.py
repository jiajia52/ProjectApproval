"""FastAPI service aligned with the auto_approval-style project layout."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.admin import router as admin_router
from app.api.routers.approvals import router as approvals_router
from app.api.routers.projects import router as projects_router
from app.api.routers.skills import router as skills_router
from app.api.routers.system import router as system_router
from app.api.routers.ui import router as ui_router

from app.core.auth.admin_auth import (
    ensure_admin_sessions,
)
from app.core.runtime.runtime_artifacts import (
    ensure_acceptance_artifacts,
    ensure_runtime_artifacts,
)
from app.core.runtime.startup_state import refresh_startup_checks

LOGGER = logging.getLogger("project_approval.startup")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    ensure_admin_sessions(app_instance)
    _, rules_bundle = ensure_runtime_artifacts(force=False)
    try:
        ensure_acceptance_artifacts(force=False)
    except Exception as exc:
        LOGGER.warning("Acceptance artifacts are unavailable during startup: %s", exc)
    checks = refresh_startup_checks(app_instance, rules_bundle=rules_bundle)
    if checks["overall_status"] == "error":
        raise RuntimeError("Critical startup checks failed. See runtime/startup_checks.json for details.")
    yield


app = FastAPI(title="Project Approval API", version="0.4.0", lifespan=lifespan)
app.include_router(ui_router)
app.include_router(admin_router)
app.include_router(skills_router)
app.include_router(system_router)
app.include_router(projects_router)
app.include_router(approvals_router)
