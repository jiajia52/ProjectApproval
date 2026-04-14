from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any

import requests
import yaml


SOURCE_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)).resolve()
PROJECT_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT
ENV_PATH = PROJECT_ROOT / ".env"
_NACOS_LOADED = False


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _strip_optional_quotes(value: str) -> str:
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        return value[1:-1]
    return value


def _parse_key_value_lines(content: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            key, sep, value = stripped.partition(":")
        if not sep:
            continue
        normalized_key = key.strip()
        if not normalized_key:
            continue
        parsed[normalized_key] = _strip_optional_quotes(value.strip())
    return parsed


def _as_env_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _coerce_mapping_to_env(data: dict[Any, Any]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, value in data.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        parsed[normalized_key] = _as_env_string(value)
    return parsed


def _parse_nacos_payload(content: str, payload_format: str) -> dict[str, str]:
    normalized_format = str(payload_format or "auto").strip().lower()

    if normalized_format in {"", "auto", "dotenv", "env", "properties"}:
        parsed = _parse_key_value_lines(content)
        if normalized_format in {"dotenv", "env", "properties"}:
            return parsed
        if parsed:
            return parsed

    if normalized_format in {"", "auto", "json"}:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = None
        if normalized_format == "json":
            if not isinstance(payload, dict):
                raise ValueError("Nacos JSON payload must be an object.")
            return _coerce_mapping_to_env(payload)
        if isinstance(payload, dict):
            converted = _coerce_mapping_to_env(payload)
            if converted:
                return converted

    if normalized_format in {"", "auto", "yaml", "yml"}:
        try:
            payload = yaml.safe_load(content)
        except yaml.YAMLError:
            payload = None
        if normalized_format in {"yaml", "yml"}:
            if not isinstance(payload, dict):
                raise ValueError("Nacos YAML payload must be a mapping.")
            return _coerce_mapping_to_env(payload)
        if isinstance(payload, dict):
            converted = _coerce_mapping_to_env(payload)
            if converted:
                return converted

    if normalized_format in {"auto", ""}:
        return {}
    raise ValueError(f"Unsupported PROJECT_APPROVAL_NACOS_FORMAT value: {payload_format}")


def _apply_environment(values: dict[str, str], *, override: bool) -> dict[str, str]:
    applied: dict[str, str] = {}
    for key, value in values.items():
        if override:
            os.environ[key] = value
            applied[key] = value
            continue
        if key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


def _parse_timeout(value: str | None, *, default: float) -> float:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        timeout = float(raw)
    except ValueError:
        return default
    return max(0.2, timeout)


def _normalize_nacos_base_url(server_addr: str) -> str:
    first = str(server_addr or "").split(",")[0].strip()
    if not first:
        return ""
    if not first.startswith(("http://", "https://")):
        scheme = str(os.getenv("PROJECT_APPROVAL_NACOS_SCHEME", "http") or "http").strip().lower() or "http"
        first = f"{scheme}://{first}"
    normalized = first.rstrip("/")
    if normalized.endswith("/nacos"):
        return normalized
    return f"{normalized}/nacos"


def _request_nacos_access_token(
    session: requests.Session,
    *,
    nacos_base_url: str,
    username: str,
    password: str,
    timeout: float,
    verify_ssl: bool,
) -> str:
    login_paths = ["/v1/auth/users/login", "/v1/auth/login"]
    for index, login_path in enumerate(login_paths):
        response = session.post(
            f"{nacos_base_url}{login_path}",
            data={"username": username, "password": password},
            timeout=timeout,
            verify=verify_ssl,
        )
        if response.status_code in {404, 405} and index < len(login_paths) - 1:
            continue
        response.raise_for_status()
        payload = response.json() if response.text else {}
        if not isinstance(payload, dict):
            return ""
        token = str(payload.get("accessToken") or "").strip()
        if token:
            return token
        nested_data = payload.get("data")
        if isinstance(nested_data, dict):
            nested_token = str(nested_data.get("accessToken") or "").strip()
            if nested_token:
                return nested_token
        return ""
    return ""


def load_env_file(env_path: Path | None = None) -> None:
    path = env_path or ENV_PATH
    if not path.exists():
        return
    parsed = _parse_key_value_lines(path.read_text(encoding="utf-8"))
    _apply_environment(parsed, override=False)


def load_nacos_env(*, force: bool = False) -> dict[str, str]:
    global _NACOS_LOADED

    if _NACOS_LOADED and not force:
        return {}

    _NACOS_LOADED = True
    enabled = parse_bool(os.getenv("PROJECT_APPROVAL_NACOS_ENABLED"), default=False)
    if not enabled:
        return {}

    server_addr = str(os.getenv("PROJECT_APPROVAL_NACOS_SERVER_ADDR", "") or "").strip()
    data_id = str(os.getenv("PROJECT_APPROVAL_NACOS_DATA_ID", "") or "").strip()
    group = str(os.getenv("PROJECT_APPROVAL_NACOS_GROUP", "DEFAULT_GROUP") or "DEFAULT_GROUP").strip()
    namespace = str(os.getenv("PROJECT_APPROVAL_NACOS_NAMESPACE", "") or "").strip()
    payload_format = str(os.getenv("PROJECT_APPROVAL_NACOS_FORMAT", "auto") or "auto").strip().lower()
    override = parse_bool(os.getenv("PROJECT_APPROVAL_NACOS_OVERRIDE"), default=False)
    fail_fast = parse_bool(os.getenv("PROJECT_APPROVAL_NACOS_FAIL_FAST"), default=False)
    verify_ssl = parse_bool(os.getenv("PROJECT_APPROVAL_NACOS_VERIFY_SSL"), default=True)
    timeout = _parse_timeout(os.getenv("PROJECT_APPROVAL_NACOS_TIMEOUT"), default=5.0)

    if not server_addr or not data_id:
        message = "PROJECT_APPROVAL_NACOS_SERVER_ADDR and PROJECT_APPROVAL_NACOS_DATA_ID are required when Nacos is enabled."
        if fail_fast:
            raise RuntimeError(message)
        warnings.warn(message)
        return {}

    nacos_base_url = _normalize_nacos_base_url(server_addr)
    if not nacos_base_url:
        message = "Invalid PROJECT_APPROVAL_NACOS_SERVER_ADDR."
        if fail_fast:
            raise RuntimeError(message)
        warnings.warn(message)
        return {}

    try:
        with requests.Session() as session:
            params = {"dataId": data_id, "group": group}
            if namespace:
                params["tenant"] = namespace

            username = str(os.getenv("PROJECT_APPROVAL_NACOS_USERNAME", "") or "").strip()
            password = str(os.getenv("PROJECT_APPROVAL_NACOS_PASSWORD", "") or "").strip()
            if username and password:
                access_token = _request_nacos_access_token(
                    session,
                    nacos_base_url=nacos_base_url,
                    username=username,
                    password=password,
                    timeout=timeout,
                    verify_ssl=verify_ssl,
                )
                if access_token:
                    params["accessToken"] = access_token

            response = session.get(
                f"{nacos_base_url}/v1/cs/configs",
                params=params,
                timeout=timeout,
                verify=verify_ssl,
            )
            response.raise_for_status()
            payload = response.text or ""
            values = _parse_nacos_payload(payload, payload_format)
            return _apply_environment(values, override=override)
    except Exception as exc:
        if fail_fast:
            raise RuntimeError("Failed to load environment values from Nacos.") from exc
        warnings.warn(f"Failed to load Nacos config: {exc}")
        return {}


def load_runtime_env(env_path: Path | None = None, *, force_nacos: bool = False) -> None:
    load_env_file(env_path)
    load_nacos_env(force=force_nacos)


load_runtime_env()
