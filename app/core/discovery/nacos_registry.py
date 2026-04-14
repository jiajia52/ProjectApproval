from __future__ import annotations

import json
import logging
import os
import random
import socket
import threading
import time
from typing import Any

import requests

LOGGER = logging.getLogger("project_approval.nacos.discovery")


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_float(value: str | None, *, default: float, min_value: float) -> float:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return max(min_value, parsed)


def _parse_int(value: str | None, *, default: int, min_value: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(min_value, parsed)


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


def _detect_local_ip() -> str:
    for probe_host in ["8.8.8.8", "1.1.1.1"]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((probe_host, 80))
                detected_ip = str(sock.getsockname()[0]).strip()
                if detected_ip and not detected_ip.startswith("127."):
                    return detected_ip
        except OSError:
            continue
    try:
        fallback = socket.gethostbyname(socket.gethostname())
    except OSError:
        fallback = ""
    return fallback.strip() or "127.0.0.1"


def _parse_metadata(raw_value: str) -> dict[str, str]:
    raw = str(raw_value or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.warning("Invalid PROJECT_APPROVAL_NACOS_DISCOVERY_METADATA JSON; ignoring metadata.")
        return {}
    if not isinstance(payload, dict):
        LOGGER.warning("PROJECT_APPROVAL_NACOS_DISCOVERY_METADATA must be a JSON object; ignoring metadata.")
        return {}
    metadata: dict[str, str] = {}
    for key, value in payload.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        metadata[normalized_key] = str(value if value is not None else "")
    return metadata


class NacosDiscoveryClient:
    def __init__(self) -> None:
        self.enabled = parse_bool(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_ENABLED"), default=False)
        self.server_addr = str(os.getenv("PROJECT_APPROVAL_NACOS_SERVER_ADDR", "") or "").strip()
        self.base_url = _normalize_nacos_base_url(self.server_addr)
        self.namespace = (
            str(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_NAMESPACE", "") or "").strip()
            or str(os.getenv("PROJECT_APPROVAL_NACOS_NAMESPACE", "") or "").strip()
        )
        self.group_name = str(
            os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_GROUP", os.getenv("PROJECT_APPROVAL_NACOS_GROUP", "DEFAULT_GROUP"))
            or "DEFAULT_GROUP"
        ).strip() or "DEFAULT_GROUP"
        self.cluster_name = str(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_CLUSTER", "DEFAULT") or "DEFAULT").strip() or "DEFAULT"
        self.service_name = str(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_SERVICE_NAME", "project-approval-api") or "").strip()
        configured_ip = str(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_IP", "") or "").strip()
        self.service_ip = configured_ip or _detect_local_ip()
        self.service_port = _parse_int(
            os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_PORT", os.getenv("PROJECT_APPROVAL_PORT", "8000")),
            default=8000,
            min_value=1,
        )
        self.weight = _parse_float(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_WEIGHT"), default=1.0, min_value=0.01)
        self.ephemeral = parse_bool(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_EPHEMERAL"), default=True)
        self.heartbeat_interval = _parse_float(
            os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_HEARTBEAT_INTERVAL"),
            default=5.0,
            min_value=1.0,
        )
        self.timeout = _parse_float(
            os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_TIMEOUT", os.getenv("PROJECT_APPROVAL_NACOS_TIMEOUT", "5")),
            default=5.0,
            min_value=0.2,
        )
        self.verify_ssl = parse_bool(
            os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_VERIFY_SSL", os.getenv("PROJECT_APPROVAL_NACOS_VERIFY_SSL", "true")),
            default=True,
        )
        self.fail_fast = parse_bool(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_FAIL_FAST"), default=False)
        self.metadata = _parse_metadata(os.getenv("PROJECT_APPROVAL_NACOS_DISCOVERY_METADATA", ""))
        self.username = str(os.getenv("PROJECT_APPROVAL_NACOS_USERNAME", "") or "").strip()
        self.password = str(os.getenv("PROJECT_APPROVAL_NACOS_PASSWORD", "") or "").strip()

        self._token_lock = threading.Lock()
        self._access_token = ""
        self._token_expires_at = 0.0
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._registered = False

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("Nacos discovery is disabled.")
        if not self.base_url:
            raise RuntimeError("Missing PROJECT_APPROVAL_NACOS_SERVER_ADDR for Nacos discovery.")
        if not self.service_name:
            raise RuntimeError("Missing PROJECT_APPROVAL_NACOS_DISCOVERY_SERVICE_NAME.")

    def _auth_token(self, *, force_refresh: bool = False) -> str:
        if not (self.username and self.password):
            return ""
        now = time.time()
        with self._token_lock:
            if not force_refresh and self._access_token and now < self._token_expires_at:
                return self._access_token
            login_paths = ["/v1/auth/users/login", "/v1/auth/login"]
            for index, login_path in enumerate(login_paths):
                response = requests.post(
                    f"{self.base_url}{login_path}",
                    data={"username": self.username, "password": self.password},
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                if response.status_code in {404, 405} and index < len(login_paths) - 1:
                    continue
                response.raise_for_status()
                payload = response.json() if response.text else {}
                if not isinstance(payload, dict):
                    break
                token = str(payload.get("accessToken") or "").strip()
                ttl_seconds = _parse_float(str(payload.get("tokenTtl") or ""), default=18000.0, min_value=60.0)
                if token:
                    self._access_token = token
                    # refresh earlier than token expiration to reduce edge failures
                    self._token_expires_at = time.time() + max(60.0, ttl_seconds - 30.0)
                    return token
                nested_data = payload.get("data")
                if isinstance(nested_data, dict):
                    nested_token = str(nested_data.get("accessToken") or "").strip()
                    if nested_token:
                        nested_ttl = _parse_float(str(nested_data.get("tokenTtl") or ""), default=18000.0, min_value=60.0)
                        self._access_token = nested_token
                        self._token_expires_at = time.time() + max(60.0, nested_ttl - 30.0)
                        return nested_token
                break
            self._access_token = ""
            self._token_expires_at = 0.0
            return ""

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> requests.Response:
        request_params = dict(params or {})
        token = self._auth_token()
        if token:
            request_params["accessToken"] = token
        response = requests.request(
            method.upper(),
            f"{self.base_url}{path}",
            params=request_params,
            timeout=timeout or self.timeout,
            verify=self.verify_ssl,
        )
        if response.status_code in {401, 403} and token:
            refreshed = self._auth_token(force_refresh=True)
            if refreshed:
                request_params["accessToken"] = refreshed
                response = requests.request(
                    method.upper(),
                    f"{self.base_url}{path}",
                    params=request_params,
                    timeout=timeout or self.timeout,
                    verify=self.verify_ssl,
                )
        response.raise_for_status()
        return response

    def _instance_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "serviceName": self.service_name,
            "groupName": self.group_name,
            "ip": self.service_ip,
            "port": self.service_port,
            "clusterName": self.cluster_name,
            "ephemeral": str(self.ephemeral).lower(),
            "weight": self.weight,
            "enabled": "true",
            "healthy": "true",
        }
        if self.metadata:
            params["metadata"] = json.dumps(self.metadata, ensure_ascii=False, separators=(",", ":"))
        if self.namespace:
            params["namespaceId"] = self.namespace
        return params

    def register(self) -> None:
        self._ensure_enabled()
        response = self._request("POST", "/v1/ns/instance", params=self._instance_params())
        response_text = (response.text or "").strip().lower()
        if response_text not in {"ok", "true", ""}:
            LOGGER.info("Nacos register response: %s", response.text)
        self._registered = True
        LOGGER.info(
            "Registered nacos instance: service=%s ip=%s port=%s group=%s cluster=%s",
            self.service_name,
            self.service_ip,
            self.service_port,
            self.group_name,
            self.cluster_name,
        )

    def deregister(self) -> None:
        if not self._registered:
            return
        try:
            self._request("DELETE", "/v1/ns/instance", params=self._instance_params())
        except Exception as exc:
            LOGGER.warning("Failed to deregister nacos instance: %s", exc)
        finally:
            self._registered = False

    def _send_beat(self) -> None:
        beat_payload: dict[str, Any] = {
            "ip": self.service_ip,
            "port": self.service_port,
            "serviceName": self.service_name,
            "cluster": self.cluster_name,
            "weight": self.weight,
            "scheduled": True,
            "metadata": self.metadata,
        }
        params: dict[str, Any] = {
            "serviceName": self.service_name,
            "groupName": self.group_name,
            "ephemeral": str(self.ephemeral).lower(),
            "beat": json.dumps(beat_payload, ensure_ascii=False, separators=(",", ":")),
        }
        if self.namespace:
            params["namespaceId"] = self.namespace
        self._request("PUT", "/v1/ns/instance/beat", params=params)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self.heartbeat_interval):
            if not self._registered:
                continue
            try:
                self._send_beat()
            except Exception as exc:
                LOGGER.warning("Failed to send nacos heartbeat: %s", exc)

    def start(self) -> bool:
        if not self.enabled:
            return False
        try:
            self.register()
            if self.ephemeral:
                self._stop_event.clear()
                self._heartbeat_thread = threading.Thread(
                    target=self._heartbeat_loop,
                    name="nacos-heartbeat",
                    daemon=True,
                )
                self._heartbeat_thread.start()
            return True
        except Exception as exc:
            if self.fail_fast:
                raise
            LOGGER.warning("Failed to start nacos discovery registration: %s", exc)
            return False

    def stop(self) -> None:
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=max(self.heartbeat_interval, 1.0))
        self._heartbeat_thread = None
        self.deregister()

    def list_instances(
        self,
        service_name: str | None = None,
        *,
        healthy_only: bool = True,
        group_name: str | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_enabled()
        resolved_service_name = str(service_name or self.service_name).strip()
        resolved_group = str(group_name or self.group_name).strip() or self.group_name
        if not resolved_service_name:
            raise ValueError("service_name is required.")

        params: dict[str, Any] = {
            "serviceName": resolved_service_name,
            "groupName": resolved_group,
            "healthyOnly": str(healthy_only).lower(),
        }
        if self.namespace:
            params["namespaceId"] = self.namespace
        response = self._request("GET", "/v1/ns/instance/list", params=params)
        payload = response.json() if response.text else {}
        hosts = payload.get("hosts") if isinstance(payload, dict) else []
        if not isinstance(hosts, list):
            return []
        return [host for host in hosts if isinstance(host, dict)]

    def choose_instance(
        self,
        service_name: str | None = None,
        *,
        healthy_only: bool = True,
        group_name: str | None = None,
    ) -> dict[str, Any] | None:
        instances = self.list_instances(service_name, healthy_only=healthy_only, group_name=group_name)
        if not instances:
            return None
        weighted: list[dict[str, Any]] = []
        for instance in instances:
            try:
                weight = float(instance.get("weight") or 1.0)
            except (TypeError, ValueError):
                weight = 1.0
            copies = max(1, int(weight))
            weighted.extend([instance] * copies)
        return random.choice(weighted or instances)

