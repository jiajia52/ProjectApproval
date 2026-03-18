#!/usr/bin/env python3
"""Dump raw iwork API responses for later structure analysis."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.approvals.iwork_client import IworkProjectClient, build_project_snapshot_requests, load_integration_config
from app.core.paths import API_DUMPS_DIR


LIST_API_PATH = "/projectEstablishment/queryProjectEstablishmentList"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump raw iwork API responses to local JSON files.")
    parser.add_argument("--project-id", action="append", dest="project_ids", default=[], help="Specific project id to dump. Can be repeated.")
    parser.add_argument("--keyword", default="", help="Project name filter for list API.")
    parser.add_argument("--page-num", type=int, default=1, help="Project list page number.")
    parser.add_argument("--page-size", type=int, default=10, help="Project list page size.")
    parser.add_argument("--max-projects", type=int, default=3, help="Max projects to dump when --project-id is not provided.")
    parser.add_argument("--output-dir", default="", help="Custom output directory.")
    parser.add_argument("--skip-list", action="store_true", help="Skip list API and only dump detail APIs for --project-id.")
    return parser.parse_args()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_filename(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]+', "_", value).strip()
    return text[:120] or "unknown"


def build_list_request_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"pageNum": args.page_num, "pageSize": args.page_size}
    if args.keyword.strip():
        payload["projectName"] = args.keyword
    return payload


def build_project_bundle_path(output_dir: Path, project_name: str, project_id: str) -> Path:
    file_name = f"{sanitize_filename(project_name)}__{sanitize_filename(project_id)}.json"
    return output_dir / "projects" / file_name


def write_project_list_file(
    output_dir: Path,
    *,
    payload: dict[str, Any],
    response: dict[str, Any] | None,
    error: dict[str, str] | None = None,
) -> None:
    projects = []
    if isinstance(response, dict):
        data = response.get("data") or {}
        raw_projects = data.get("dataList") or []
        projects = [
            {
                "project_id": str(project.get("id") or project.get("project_id") or ""),
                "project_name": str(project.get("projectName") or project.get("project_id") or ""),
            }
            for project in raw_projects
            if isinstance(project, dict)
        ]
    write_json(
        output_dir / "project_list.json",
        {
            "api_name": "project_list",
            "request": {"method": "POST", "path": LIST_API_PATH, "payload": payload},
            "response": response,
            "error": error,
            "project_count": len(projects),
            "projects": projects,
        },
    )


def dump_list_response(
    client: IworkProjectClient,
    args: argparse.Namespace,
    output_dir: Path,
    errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    payload = build_list_request_payload(args)
    result = client.request_json("POST", LIST_API_PATH, payload=payload, strict=False)
    write_project_list_file(output_dir, payload=payload, response=result)
    if result.get("code") not in (None, 0):
        errors.append({"stage": "project_list", "message": str(result.get("message") or "Project list API returned a business error.")})
    data = result.get("data") or {}
    return data.get("dataList") or []


def dump_project_responses(client: IworkProjectClient, project: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    project_id = str(project.get("id") or project.get("project_id") or "").strip()
    project_name = str(project.get("projectName") or project_id or "unknown")
    bundle_path = build_project_bundle_path(output_dir, project_name, project_id)
    bundle: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_id": project_id,
        "project_name": project_name,
        "project_summary": project,
        "endpoints": {},
        "errors": [],
    }

    for endpoint in build_project_snapshot_requests(project_id):
        endpoint_name = endpoint["name"]
        method = endpoint["method"]
        path = endpoint["path"]
        payload = endpoint["payload"]
        record: dict[str, Any] = {"name": endpoint_name, "method": method, "path": path, "payload": payload}
        try:
            response = client.request_json(method, path, payload=payload, strict=False)
            record["response"] = response
            record["ok"] = response.get("code") == 0
            record["code"] = response.get("code")
            record["message"] = response.get("message")
            if record["code"] not in (None, 0):
                bundle["errors"].append(
                    {
                        "stage": "project_endpoint",
                        "project_id": project_id,
                        "endpoint": endpoint_name,
                        "message": str(record["message"] or "Project detail API returned a business error."),
                    }
                )
        except Exception as exc:
            record["ok"] = False
            record["message"] = str(exc)
            record["error"] = {"error_type": type(exc).__name__, "message": str(exc)}
            bundle["errors"].append(
                {
                    "stage": "project_endpoint",
                    "project_id": project_id,
                    "endpoint": endpoint_name,
                    "message": str(exc),
                }
            )
        bundle["endpoints"][endpoint_name] = record

    write_json(bundle_path, bundle)
    return {
        "project_id": project_id,
        "project_name": project_name,
        "file_path": str(bundle_path.relative_to(output_dir)),
        "endpoint_count": len(bundle["endpoints"]),
        "errors": bundle["errors"],
    }


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else API_DUMPS_DIR / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_integration_config()
    client = IworkProjectClient(config)

    projects: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    if args.project_ids:
        projects = [{"id": project_id, "projectName": project_id} for project_id in args.project_ids]
    elif not args.skip_list:
        try:
            projects = dump_list_response(client, args, output_dir, errors)
            projects = projects[: max(args.max_projects, 0)]
        except Exception as exc:
            error = {"stage": "project_list", "message": str(exc)}
            errors.append(error)
            write_project_list_file(output_dir, payload=build_list_request_payload(args), response=None, error=error)
    else:
        errors.append({"stage": "arguments", "message": "Using --skip-list requires at least one --project-id."})

    summaries: list[dict[str, Any]] = []
    for project in projects:
        try:
            summaries.append(dump_project_responses(client, project, output_dir))
        except Exception as exc:
            errors.append({"stage": "project_dump", "project_id": str(project.get("id", "")), "message": str(exc)})

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "project_count": len(projects),
        "projects": summaries,
        "errors": errors,
    }
    write_json(output_dir / "dump_manifest.json", manifest)

    print(f"Output directory: {output_dir}")
    print(f"Project count: {len(projects)}")
    print(f"Error count: {len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
