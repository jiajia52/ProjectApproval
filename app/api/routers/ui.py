from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.core.web.frontend_serving import (
    ensure_frontend_dev_server,
    frontend_dev_redirect,
    frontend_dev_server_available,
    frontend_index_file,
    resolve_frontend_file,
)
from app.core.config.scenes import normalize_scene

router = APIRouter()


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/initiation")


@router.get("/ui")
@router.get("/ui/")
def ui_root(request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path="/" if request.url.path.endswith("/") else "", query=request.url.query)
    return FileResponse(frontend_index_file())


@router.get("/ui/index.html", include_in_schema=False)
def ui_legacy_index() -> RedirectResponse:
    return RedirectResponse(url="/ui/initiation")


@router.get("/ui/approval", include_in_schema=False)
def ui_approval() -> Response:
    return RedirectResponse(url="/ui/initiation/projects")


@router.get("/ui/approval.html", include_in_schema=False)
def ui_legacy_approval() -> Response:
    return RedirectResponse(url="/ui/initiation/projects")


@router.get("/ui/workbench.html", include_in_schema=False)
def ui_legacy_workbench(projectId: str | None = None) -> Response:
    query = f"?projectId={projectId}" if projectId else ""
    return RedirectResponse(url=f"/ui/workbench{query}")


@router.get("/ui/workbench", include_in_schema=False)
def ui_workbench(request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path="workbench", query=request.url.query)
    return FileResponse(frontend_index_file())


@router.get("/ui/skills.html", include_in_schema=False)
def ui_legacy_skills() -> Response:
    return RedirectResponse(url="/ui/initiation/skills")


@router.get("/ui/rules.html", include_in_schema=False)
def ui_legacy_rules() -> Response:
    return RedirectResponse(url="/ui/initiation/skills")


@router.get("/ui/project-viewer.html", include_in_schema=False)
def ui_legacy_project_viewer(
    projectId: str,
    category: str | None = None,
    scene: str | None = None,
) -> Response:
    query_params: dict[str, str] = {}
    if category:
        query_params["category"] = category
    if scene:
        query_params["scene"] = normalize_scene(scene)
    query = f"?{urlencode(query_params)}" if query_params else ""
    return RedirectResponse(url=f"/ui/project/{projectId}{query}")


@router.get("/ui/project/{project_id}", include_in_schema=False)
def ui_project(project_id: str, request: Request, category: str | None = None) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path=f"project/{project_id}", query=request.url.query)
    return FileResponse(frontend_index_file())


@router.get("/ui/skills", include_in_schema=False)
def ui_skills() -> Response:
    return RedirectResponse(url="/ui/initiation/skills")


@router.get("/ui/initiation", include_in_schema=False)
@router.get("/ui/acceptance", include_in_schema=False)
@router.get("/ui/task-order", include_in_schema=False)
@router.get("/ui/initiation/projects", include_in_schema=False)
@router.get("/ui/initiation/review-feedback", include_in_schema=False)
@router.get("/ui/initiation/skills", include_in_schema=False)
@router.get("/ui/acceptance/projects", include_in_schema=False)
@router.get("/ui/acceptance/review-feedback", include_in_schema=False)
@router.get("/ui/acceptance/skills", include_in_schema=False)
@router.get("/ui/task-order/projects", include_in_schema=False)
@router.get("/ui/task-order/review-feedback", include_in_schema=False)
@router.get("/ui/task-order/skills", include_in_schema=False)
def ui_scene_pages(request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path=request.url.path.removeprefix("/ui/"), query=request.url.query)
    return FileResponse(frontend_index_file())


@router.get("/ui/{full_path:path}", include_in_schema=False)
def ui_files(full_path: str, request: Request) -> Response:
    ensure_frontend_dev_server()
    if frontend_dev_server_available():
        return frontend_dev_redirect(path=full_path, query=request.url.query)
    file_path = resolve_frontend_file(full_path)
    if file_path is not None:
        return FileResponse(file_path)
    return FileResponse(frontend_index_file())
