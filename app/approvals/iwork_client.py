"""HTTP client for fetching real project data from iwork/ITPM APIs."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import uuid
import warnings
from copy import deepcopy
from concurrent import futures
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

from app.core.paths import API_RESULT_DIR, INTEGRATION_CONFIG_PATH

_SNAPSHOT_CACHE_LOCK = threading.Lock()
_SNAPSHOT_CACHE: dict[str, dict[str, Any]] = {}


def read_json(path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_file_stem(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "api"


def write_api_result(
    *,
    api_name: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    project_id: str | None = None,
    result: Any = None,
    error: str | None = None,
) -> Path:
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S-%f")
    output_dir = API_RESULT_DIR
    normalized_project_id = sanitize_file_stem(str(project_id or "").strip()) if project_id else ""
    if normalized_project_id:
        output_dir = API_RESULT_DIR / "projects" / normalized_project_id
    output_path = output_dir / f"{timestamp}_{sanitize_file_stem(api_name)}.json"
    record = {
        "api_name": api_name,
        "method": method.upper(),
        "path": path,
        "payload": payload,
        "project_id": project_id or "",
        "result": result,
        "error": error or "",
        "called_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
    }
    write_json(output_path, record)
    return output_path


def _extract_project_list_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or {}
    data = result.get("data") or {}
    records = data.get("dataList")
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    return []


def infer_project_id(path: str, payload: dict[str, Any] | None = None, explicit_project_id: str | None = None) -> str:
    if explicit_project_id:
        return str(explicit_project_id).strip()

    if isinstance(payload, dict):
        for key in ["projectId", "project_id", "id"]:
            value = str(payload.get(key, "") or "").strip()
            if value:
                return value

    normalized_path = str(path or "").strip()
    if not normalized_path:
        return ""
    if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
        normalized_path = urllib.parse.urlparse(normalized_path).path

    for pattern in [
        r"/projectUploading/list/([^/?#]+)",
        r"/project/goal/get/([^/?#]+)",
        r"/value/info(?:NoTam)?/([^/?#]+)",
        r"/milestone/newList/([^/?#]+)",
        r"/budget/info/([^/?#]+)",
        r"/change/list/([^/?#]+)",
        r"/projectOrgFramework/list/([^/?#]+)",
    ]:
        match = re.search(pattern, normalized_path)
        if match:
            return match.group(1).strip()
    return ""


def load_cached_project_list(
    *,
    page_num: int,
    page_size: int,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    candidates: list[tuple[int, float, Path, dict[str, Any], list[dict[str, Any]]]] = []
    for path in API_RESULT_DIR.rglob("*_project_list.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue
        result = payload.get("result") or {}
        records = _extract_project_list_records(payload)
        if result.get("code") != 0 or not records:
            continue
        try:
            modified_time = path.stat().st_mtime
        except Exception:
            modified_time = 0.0
        candidates.append((len(records), modified_time, path, payload, records))

    if not candidates:
        return None

    _, _, cache_path, cache_payload, cache_records = max(candidates, key=lambda item: (item[0], item[1]))
    normalized_projects = [normalize_project_summary(item) for item in cache_records]
    if filters:
        project_name = str(filters.get("projectName", "") or "").strip()
        if project_name:
            normalized_projects = [
                project for project in normalized_projects if _match_text(project.get("projectName"), project_name)
            ]

    total_available = len(normalized_projects)
    start = max(page_num - 1, 0) * max(page_size, 1)
    end = start + max(page_size, 1)
    paged_projects = normalized_projects[start:end]
    return {
        "raw": cache_payload.get("result") or {},
        "projects": paged_projects,
        "total": total_available,
        "code": 0,
        "message": "Loaded project list from local cache because the remote list API failed.",
        "source": "cache",
        "warning": "Remote list API failed; showing the latest successful cached project list.",
        "cache_file": str(cache_path),
    }


def load_cached_project_summary(project_id: str) -> dict[str, Any] | None:
    candidate_records: list[tuple[float, dict[str, Any]]] = []
    for path in API_RESULT_DIR.rglob("*_project_list.json"):
        try:
            payload = read_json(path)
            records = _extract_project_list_records(payload)
        except Exception:
            continue
        for item in records:
            normalized = normalize_project_summary(item)
            if str(normalized.get("id") or "").strip() != str(project_id).strip():
                continue
            try:
                modified_time = path.stat().st_mtime
            except Exception:
                modified_time = 0.0
            candidate_records.append((modified_time, normalized))
            break
    if not candidate_records:
        return None
    _, summary = max(candidate_records, key=lambda item: item[0])
    return summary


def _build_snapshot_endpoint_from_cache_record(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("result")
    error = str(record.get("error") or "").strip()
    if isinstance(result, dict) and any(key in result for key in ["code", "message", "data"]):
        code = result.get("code")
        message = str(result.get("message") or error)
        data = result.get("data")
        ok = code == 0 and not error
        return {"ok": ok, "code": code, "message": message, "data": data}
    return {"ok": not error, "code": 0 if not error else -1, "message": error, "data": result}


def load_cached_project_snapshot(project_id: str) -> dict[str, Any] | None:
    project_dir = API_RESULT_DIR / "projects" / sanitize_file_stem(str(project_id or "").strip())
    if not project_dir.exists():
        return None

    latest_records: dict[str, tuple[float, dict[str, Any]]] = {}
    for path in project_dir.glob("*.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue
        api_name = str(payload.get("api_name") or "").strip()
        if not api_name:
            continue
        try:
            modified_time = path.stat().st_mtime
        except Exception:
            modified_time = 0.0
        current = latest_records.get(api_name)
        if current is not None and current[0] >= modified_time:
            continue
        latest_records[api_name] = (modified_time, payload)

    if not latest_records:
        return None

    endpoints = {
        api_name: _build_snapshot_endpoint_from_cache_record(payload)
        for api_name, (_, payload) in latest_records.items()
    }
    return {"project_id": project_id, "endpoints": endpoints, "source": "api_result_cache"}


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def snapshot_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_SNAPSHOT_CACHE_TTL", "45") or "45").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 45
    return max(0, min(ttl, 300))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
            continue
        if value not in (None, ""):
            merged[key] = value
    return merged


def normalize_bearer(token: str) -> str:
    token = token.strip()
    if not token:
        return ""
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def extract_token_from_url(raw_value: str) -> str:
    value = raw_value.strip()
    if not value or "token=" not in value:
        return ""
    parsed = urllib.parse.urlparse(value)
    token = (urllib.parse.parse_qs(parsed.query).get("token") or [""])[0].strip()
    return normalize_bearer(token) if token else ""


def normalize_token_input(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://") or "token=" in value:
        return extract_token_from_url(value)
    return normalize_bearer(value)


def infer_fixed_project(project: dict[str, Any]) -> bool | None:
    direct = first_non_empty(
        project.get("fixedProject"),
        project.get("isFixedProject"),
        project.get("fixedFlag"),
        project.get("isFixed"),
    )
    if isinstance(direct, bool):
        return direct
    if isinstance(direct, (int, float)):
        return bool(direct)
    if isinstance(direct, str):
        normalized = direct.strip().lower()
        if normalized in {"是", "y", "yes", "true", "1"}:
            return True
        if normalized in {"否", "n", "no", "false", "0"}:
            return False

    for value in [
        project.get("projectFeeTypeName"),
        project.get("projectTypeName"),
        project.get("projectCategoryName"),
        project.get("projectSourceName"),
    ]:
        if isinstance(value, str) and "固定" in value:
            return True

    long_term_flag = project.get("longTermFlag")
    if isinstance(long_term_flag, str):
        normalized = long_term_flag.strip().lower()
        if normalized in {"是", "yes", "true", "1"}:
            return True
        if normalized in {"否", "no", "false", "0"}:
            return False

    return None


def normalize_project_summary(project: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(project)
    fixed_project = infer_fixed_project(project)
    normalized["projectCode"] = first_non_empty(project.get("projectCode"), project.get("serialNo"))
    normalized["domainName"] = first_non_empty(
        project.get("domainName"),
        project.get("belongTeamName"),
        project.get("businessDomainName"),
        project.get("belongAreaName"),
    )
    normalized["departmentName"] = first_non_empty(
        project.get("departmentName"),
        project.get("belongDepartmentName"),
        project.get("businessDepartmentName"),
        project.get("deptName"),
    )
    normalized["managerName"] = first_non_empty(
        project.get("projectManagerName"),
        project.get("projectLeaderName"),
        project.get("managerName"),
    )
    normalized["projectCategoryName"] = first_non_empty(
        project.get("projectCategoryName"),
        project.get("projectFeeTypeName"),
        project.get("projectTypeName"),
    )
    normalized["projectTypeName"] = first_non_empty(
        project.get("projectTypeName"),
        project.get("projectFeeTypeName"),
        project.get("projectCategoryName"),
    )
    normalized["fixedProject"] = fixed_project
    normalized["fixedProjectLabel"] = "是" if fixed_project is True else "否" if fixed_project is False else "未知"
    normalized["projectStatusName"] = first_non_empty(project.get("projectStatusName"), project.get("projectStatus"))
    normalized["flowStatusDisplay"] = first_non_empty(project.get("flowStatusName"), project.get("flowStatus"))
    return normalized


def _match_text(candidate: Any, expected: str) -> bool:
    if not expected:
        return True
    return expected.strip().lower() in str(candidate or "").strip().lower()


def matches_project_filters(project: dict[str, Any], filters: dict[str, Any] | None = None) -> bool:
    if not filters:
        return True
    text_filters = {
        "project_name": [project.get("projectName"), project.get("name")],
        "project_code": [project.get("projectCode"), project.get("serialNo")],
        "domain": [project.get("domainName"), project.get("belongTeamName")],
        "department": [project.get("departmentName"), project.get("belongDepartmentName")],
        "project_manager": [project.get("managerName"), project.get("projectManagerName")],
        "project_type": [project.get("projectTypeName"), project.get("projectFeeTypeName")],
        "project_category": [project.get("projectCategoryName"), project.get("projectFeeTypeName")],
        "project_status": [project.get("projectStatusName"), project.get("projectStatus")],
        "flow_status": [project.get("flowStatusDisplay"), project.get("flowStatusName"), project.get("flowStatus")],
    }
    for key, candidates in text_filters.items():
        expected = str(filters.get(key, "") or "").strip()
        if expected and not any(_match_text(candidate, expected) for candidate in candidates):
            return False

    fixed_filter = str(filters.get("fixed_project", "") or "").strip().lower()
    if fixed_filter:
        inferred = project.get("fixedProject")
        if fixed_filter in {"true", "1", "yes", "是"} and inferred is not True:
            return False
        if fixed_filter in {"false", "0", "no", "否"} and inferred is not False:
            return False
    return True


def integration_env_defaults() -> dict[str, Any]:
    base_url = os.getenv(
        "PROJECT_APPROVAL_IWORK_BASE_URL",
        "https://prod-itpm.faw.cn/itpmNew/gateway/sop-itpm-service",
    )
    iam_url = os.getenv(
        "PROJECT_APPROVAL_IWORK_IAM_URL",
        "https://iwork.faw.cn/api-dev/dcp-base-sso/iamToken",
    )
    return {
        "base_url": base_url,
        "iam_url": iam_url,
        "token": normalize_token_input(os.getenv("PROJECT_APPROVAL_IWORK_TOKEN", "").strip()),
        "jsessionid": os.getenv("PROJECT_APPROVAL_IWORK_JSESSIONID", "").strip(),
        "use_iam": parse_bool(os.getenv("PROJECT_APPROVAL_IWORK_USE_IAM"), default=False),
        "iam_full_url": os.getenv("PROJECT_APPROVAL_IWORK_IAM_FULL_URL", "").strip(),
        "iam_code": os.getenv("PROJECT_APPROVAL_IWORK_IAM_CODE", "").strip(),
        "client_id": os.getenv("PROJECT_APPROVAL_IWORK_CLIENT_ID", "faw_qfc_sso").strip(),
        "secret_path": os.getenv("PROJECT_APPROVAL_IWORK_SECRET_PATH", "iworkiamencrypt.client-secret").strip(),
        "redirect_url": os.getenv("PROJECT_APPROVAL_IWORK_REDIRECT_URL", iam_url).strip(),
        "index_url": os.getenv("PROJECT_APPROVAL_IWORK_INDEX_URL", "https://iwork.faw.cn").strip(),
        "tenant_id": os.getenv("PROJECT_APPROVAL_IWORK_TENANT_ID", "YQJT").strip(),
        "system_id": os.getenv("PROJECT_APPROVAL_IWORK_SYSTEM_ID", "BA-0222").strip(),
        "menu_code": os.getenv("PROJECT_APPROVAL_IWORK_MENU_CODE", "null").strip(),
        "logo": os.getenv("PROJECT_APPROVAL_IWORK_LOGO", "iworkiamencrypt").strip(),
        "state": os.getenv("PROJECT_APPROVAL_IWORK_STATE", "123").strip(),
        "timeout": int(os.getenv("PROJECT_APPROVAL_IWORK_TIMEOUT", "20") or 20),
        "verify_ssl": parse_bool(os.getenv("PROJECT_APPROVAL_IWORK_VERIFY_SSL"), default=True),
        "ca_bundle_path": os.getenv("PROJECT_APPROVAL_IWORK_CA_BUNDLE_PATH", "").strip(),
        "headers": {
            "lang": os.getenv("PROJECT_APPROVAL_IWORK_LANG", "zh-cn").strip(),
            "qfcsid": os.getenv("PROJECT_APPROVAL_IWORK_QFCSID", "MS-0701").strip(),
            "qfctid": os.getenv("PROJECT_APPROVAL_IWORK_QFCTID", "YQJT").strip(),
            "qfc-user-para": os.getenv(
                "PROJECT_APPROVAL_IWORK_QFC_USER_PARA",
                '{"systemId":"MS-0701","appCode":"MS-0701_APP_004"}',
            ).strip(),
        },
    }


def build_project_snapshot_requests(project_id: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "project_base_info",
            "method": "POST",
            "path": "/projectBaseInfo/info",
            "payload": {"projectId": project_id},
        },
        {"name": "project_uploading", "method": "GET", "path": f"/projectUploading/list/{project_id}", "payload": None},
        {"name": "project_goal", "method": "GET", "path": f"/project/goal/get/{project_id}", "payload": None},
        {"name": "project_scope_dev", "method": "POST", "path": "/projectBaseInfo/eamapAndSystem", "payload": {"projectId": project_id}},
        {
            "name": "project_scope_ops",
            "method": "POST",
            "path": "/project/range/list",
            "payload": {"projectId": project_id},
        },
        {
            "name": "project_scope_ops_get_scope",
            "method": "POST",
            "path": "/projectBaseInfo/getProjectScope",
            "payload": {"projectId": project_id},
        },
        {
            "name": "project_scope_ops_legacy",
            "method": "POST",
            "path": "/projectBaseInfo/projectRange/list",
            "payload": {"projectId": project_id},
        },
        {
            "name": "system_scope_okr",
            "method": "POST",
            "path": "/projectBaseInfo/eamapAndSystemOkr",
            "payload": {"projectId": project_id},
        },
        {"name": "system_scope", "method": "POST", "path": "/projectMicosInfo/getList", "payload": {"projectId": project_id}},
        {"name": "tam_info", "method": "GET", "path": f"/value/info/{project_id}", "payload": None},
        {"name": "project_value", "method": "GET", "path": f"/value/infoNoTam/{project_id}", "payload": None},
        {"name": "milestones", "method": "GET", "path": f"/milestone/newList/{project_id}", "payload": None},
        {
            "name": "organization",
            "method": "POST",
            "path": "/organizationalStructure/queryOrganizationNumber",
            "payload": {"projectId": project_id, "pageNo": 1, "pageSize": 200},
        },
        {
            "name": "organization_framework",
            "method": "GET",
            "path": f"/projectOrgFramework/list/{project_id}",
            "payload": None,
        },
        {
            "name": "organization_flag_0",
            "method": "POST",
            "path": "/organizationalStructure/queryOrganizationNumber",
            "payload": {"projectId": project_id, "pageNo": 1, "pageSize": 200, "flag": 0},
        },
        {
            "name": "organization_flag_1",
            "method": "POST",
            "path": "/organizationalStructure/queryOrganizationNumber",
            "payload": {"projectId": project_id, "pageNo": 1, "pageSize": 200, "flag": 1},
        },
        {"name": "budget", "method": "GET", "path": f"/budget/info/{project_id}", "payload": None},
        {"name": "cost_change", "method": "GET", "path": f"/change/list/{project_id}", "payload": None},
    ]


def read_persisted_integration_config() -> dict[str, Any]:
    if not INTEGRATION_CONFIG_PATH.exists():
        return {}
    return read_json(INTEGRATION_CONFIG_PATH)


def load_integration_config() -> dict[str, Any]:
    config = integration_env_defaults()
    persisted = read_persisted_integration_config()
    if persisted:
        config = deep_merge(config, persisted)
    return config


def save_integration_config(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(payload, ensure_ascii=False))
    token = sanitized.get("token")
    if isinstance(token, str):
        sanitized["token"] = normalize_token_input(token) if token.strip() else ""
    ca_bundle_path = sanitized.get("ca_bundle_path")
    if isinstance(ca_bundle_path, str):
        sanitized["ca_bundle_path"] = ca_bundle_path.strip()
    write_json(INTEGRATION_CONFIG_PATH, sanitized)
    return load_integration_config()


class RemoteAPIError(RuntimeError):
    """Represents a business-level error returned by the remote API."""

    def __init__(self, code: Any, message: str, payload: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.payload = payload or {}
        super().__init__(message)


class IworkProjectClient:
    """Thin wrapper around the ITPM project APIs."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.base_url = config["base_url"].rstrip("/")
        self.timeout = int(config.get("timeout", 20))
        self.verify_ssl = bool(config.get("verify_ssl", True))
        self.ca_bundle_path = str(config.get("ca_bundle_path", "") or "").strip()
        self.verify_option: bool | str = self._resolve_verify_option()
        self.session = requests.Session()
        self.session.trust_env = False

    def _resolve_verify_option(self) -> bool | str:
        if not self.verify_ssl:
            return False
        if self.ca_bundle_path:
            if not Path(self.ca_bundle_path).exists():
                raise FileNotFoundError(f"CA bundle path not found: {self.ca_bundle_path}")
            return self.ca_bundle_path
        return True

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        request_kwargs = dict(kwargs)
        request_kwargs.setdefault("timeout", self.timeout)
        request_kwargs["verify"] = self.verify_option
        if self.verify_option is False:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                return self.session.request(method=method, url=url, **request_kwargs)
        return self.session.request(method=method, url=url, **request_kwargs)

    def build_headers(self, token: str | None = None) -> dict[str, str]:
        headers_config = self.config.get("headers", {})
        active_token = normalize_bearer(token or self.config.get("token", ""))
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "authorization": active_token,
            "content-type": "application/json",
            "gray": "",
            "lang": headers_config.get("lang", "zh-cn"),
            "origin": "https://iwork.faw.cn",
            "qfc-user-para": headers_config.get("qfc-user-para", ""),
            "qfcsid": headers_config.get("qfcsid", "MS-0701"),
            "qfctid": headers_config.get("qfctid", "YQJT"),
            "referer": "https://iwork.faw.cn/",
            "sw8": "",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            "useragent": "pc",
            "x-traceid": uuid.uuid4().hex[:16],
        }
        jsessionid = self.config.get("jsessionid", "").strip()
        if jsessionid:
            headers["cookie"] = f"JSESSIONID={jsessionid}"
        return headers

    def fetch_token_from_iam(self) -> str:
        raw_url = str(self.config.get("iam_full_url", "")).strip()
        direct_token = extract_token_from_url(raw_url)
        if direct_token:
            return direct_token

        if raw_url:
            url = raw_url
        else:
            query = {
                "clientId": self.config.get("client_id", ""),
                "secretPath": self.config.get("secret_path", ""),
                "redirectUrl": self.config.get("redirect_url", ""),
                "indexUrl": self.config.get("index_url", ""),
                "tenantId": self.config.get("tenant_id", ""),
                "systemId": self.config.get("system_id", ""),
                "menuCode": self.config.get("menu_code", ""),
                "logo": self.config.get("logo", ""),
            }
            if self.config.get("iam_code"):
                query["code"] = self.config["iam_code"]
                query["state"] = self.config.get("state", "123")
            url = f"{self.config['iam_url']}?{urllib.parse.urlencode(query)}"

        response = self._request(
            "GET",
            url,
            headers={
                "referer": "https://iam.faw.cn/",
                "user-agent": "Mozilla/5.0",
                "cookie": f"JSESSIONID={self.config.get('jsessionid', '')}",
            },
            allow_redirects=True,
        )

        redirect_token = extract_token_from_url(response.url)
        if redirect_token:
            return redirect_token

        payload: Any = {}
        try:
            payload = response.json()
        except Exception:
            payload = {}

        if isinstance(payload, dict):
            token = (
                payload.get("token")
                or (payload.get("data") or {}).get("token")
                or (payload.get("data") or {}).get("accessToken")
            )
            if isinstance(token, str) and token.strip():
                return normalize_bearer(token)
            message = json.dumps(payload, ensure_ascii=False)
            raise RuntimeError(f"无法从 iamToken 刷新 token: {message}")
        raise RuntimeError("无法从 iamToken 刷新 token，请提供有效的 token 或 iam 回调地址。")

    def refresh_token(self) -> str:
        token = self.fetch_token_from_iam()
        self.config["token"] = token
        persisted = read_persisted_integration_config()
        persisted["token"] = token
        write_json(INTEGRATION_CONFIG_PATH, persisted)
        return token

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
        strict: bool = False,
        api_name: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        effective_api_name = api_name or path
        resolved_project_id = infer_project_id(path, payload=payload, explicit_project_id=project_id)
        response = self._request(
            method.upper(),
            url,
            headers=self.build_headers(token),
            json=payload,
        )
        try:
            response.raise_for_status()
            result = response.json()
            write_api_result(
                api_name=effective_api_name,
                method=method,
                path=path,
                payload=payload,
                project_id=resolved_project_id,
                result=result,
            )
            if strict and isinstance(result, dict):
                code = result.get("code")
                if code not in (None, 0):
                    raise RemoteAPIError(code=code, message=str(result.get("message") or "远程接口调用失败"), payload=result)
            return result
        except Exception as exc:
            result_payload: Any = None
            try:
                result_payload = response.json()
            except Exception:
                result_payload = {"status_code": response.status_code, "text": response.text[:2000]}
            write_api_result(
                api_name=effective_api_name,
                method=method,
                path=path,
                payload=payload,
                project_id=resolved_project_id,
                result=result_payload,
                error=str(exc),
            )
            raise

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
        api_name: str | None = None,
        project_id: str | None = None,
    ) -> tuple[bytes, str]:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = self.build_headers(token)
        headers.pop("content-type", None)
        effective_api_name = api_name or path
        resolved_project_id = infer_project_id(path, payload=payload, explicit_project_id=project_id)
        response = self._request(
            method.upper(),
            url,
            headers=headers,
            json=payload,
        )
        try:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "application/octet-stream")
            write_api_result(
                api_name=effective_api_name,
                method=method,
                path=path,
                payload=payload,
                project_id=resolved_project_id,
                result={
                    "content_type": content_type,
                    "content_length": len(response.content),
                    "status_code": response.status_code,
                },
            )
            return response.content, content_type
        except Exception as exc:
            write_api_result(
                api_name=effective_api_name,
                method=method,
                path=path,
                payload=payload,
                project_id=resolved_project_id,
                result={
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "text": response.text[:2000],
                },
                error=str(exc),
            )
            raise

    def download_file(self, file_path: str) -> tuple[bytes, str]:
        normalized = str(file_path or "").strip()
        if not normalized:
            raise ValueError("缺少文件路径")
        if normalized.startswith("http://") or normalized.startswith("https://"):
            path = normalized
        else:
            path = f"/files/download/{normalized.lstrip('/')}"
        return self.request_bytes("GET", path, api_name="file_download")

    def list_projects(
        self,
        *,
        page_num: int = 1,
        page_size: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"pageNum": page_num, "pageSize": page_size}
        if filters:
            payload.update(filters)
        try:
            result = self.request_json(
                "POST",
                "/projectEstablishment/queryProjectEstablishmentList",
                payload=payload,
                strict=True,
                api_name="project_list",
            )
            data = result.get("data") or {}
            projects = [normalize_project_summary(item) for item in (data.get("dataList") or [])]
            return {
                "raw": result,
                "projects": projects,
                "total": data.get("total", 0),
                "code": result.get("code"),
                "message": result.get("message"),
                "source": "remote",
                "warning": "",
            }
        except Exception:
            cached = load_cached_project_list(page_num=page_num, page_size=page_size, filters=filters)
            if cached is not None:
                return cached
            raise

    def list_project_statuses(self) -> list[dict[str, Any]]:
        result = self.request_json(
            "GET",
            "/projectCenter/queryProjectStatusList",
            strict=True,
            api_name="project_status_options",
        )
        data = result.get("data") or {}
        return data.get("statusList") or []

    def fetch_project_snapshot(self, project_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        cache_key = str(project_id or "").strip()
        ttl_seconds = snapshot_cache_ttl_seconds()
        now = time.monotonic()
        if cache_key and ttl_seconds > 0 and not force_refresh:
            with _SNAPSHOT_CACHE_LOCK:
                cached_entry = _SNAPSHOT_CACHE.get(cache_key)
                if cached_entry and float(cached_entry.get("expires_at") or 0) > now:
                    return deepcopy(cached_entry.get("snapshot") or {"project_id": project_id, "endpoints": {}})
                if cached_entry:
                    _SNAPSHOT_CACHE.pop(cache_key, None)

        snapshot: dict[str, Any] = {"project_id": project_id, "endpoints": {}}
        endpoints = build_project_snapshot_requests(project_id)
        if not endpoints:
            return snapshot

        default_workers = 6
        try:
            max_workers = int(os.getenv("PROJECT_APPROVAL_SNAPSHOT_MAX_WORKERS", str(default_workers)) or default_workers)
        except ValueError:
            max_workers = default_workers
        max_workers = max(2, min(max_workers, len(endpoints)))

        endpoint_results: dict[str, dict[str, Any]] = {}

        def run_endpoint(endpoint: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            name = endpoint["name"]
            method = endpoint["method"]
            path = endpoint["path"]
            payload = endpoint["payload"]
            try:
                response = self.request_json(
                    method,
                    path,
                    payload=payload,
                    strict=False,
                    api_name=name,
                    project_id=project_id,
                )
                return name, {
                    "ok": response.get("code") == 0,
                    "code": response.get("code"),
                    "message": response.get("message"),
                    "data": response.get("data"),
                }
            except Exception as exc:
                return name, {
                    "ok": False,
                    "code": -1,
                    "message": str(exc),
                    "data": None,
                }

        with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(run_endpoint, endpoint): endpoint["name"] for endpoint in endpoints}
            for future in futures.as_completed(future_map):
                endpoint_name = future_map[future]
                try:
                    name, payload = future.result()
                except Exception as exc:
                    name = endpoint_name
                    payload = {
                        "ok": False,
                        "code": -1,
                        "message": str(exc),
                        "data": None,
                    }
                endpoint_results[name] = payload

        for endpoint in endpoints:
            name = endpoint["name"]
            snapshot["endpoints"][name] = endpoint_results.get(
                name,
                {
                    "ok": False,
                    "code": -1,
                    "message": "Missing endpoint result",
                    "data": None,
                },
            )

        if cache_key and ttl_seconds > 0:
            with _SNAPSHOT_CACHE_LOCK:
                _SNAPSHOT_CACHE[cache_key] = {
                    "expires_at": time.monotonic() + ttl_seconds,
                    "snapshot": deepcopy(snapshot),
                }
        return snapshot
