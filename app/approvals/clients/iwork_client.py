"""HTTP client for fetching real project data from iwork/ITPM APIs."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import uuid
import warnings
from copy import deepcopy
from concurrent import futures
from pathlib import Path
from typing import Any

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from app.approvals.clients.iwork_client_api_cache import (
    _PROJECT_PARAM_CACHE,
    _PROJECT_PARAM_CACHE_LOCK,
    _SNAPSHOT_CACHE,
    _SNAPSHOT_CACHE_LOCK,
    _TASK_ORDER_STATUS_CACHE,
    _TASK_ORDER_STATUS_CACHE_LOCK,
    api_result_search_dirs,
    infer_project_id,
    load_cached_acceptance_review_projects,
    project_param_cache_ttl_seconds,
    read_json,
    sanitize_file_stem,
    store_acceptance_review_projects_cache,
    write_api_result,
    write_json,
)
from app.approvals.clients.iwork_client_snapshot_profiles import (
    aggregate_acceptance_detail_results,
    build_acceptance_detail_requests,
    build_acceptance_snapshot_requests,
    build_project_snapshot_requests,
    collect_accept_ids,
    extract_establishment_project_id,
)
from app.core.config.paths import INTEGRATION_CONFIG_PATH
from app.core.config.scenes import normalize_scene

LOGGER = logging.getLogger("project_approval.iwork_client")

def _extract_project_list_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or {}
    data = result.get("data") or {}
    records = data.get("dataList")
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    return []


def _extract_task_order_list_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or {}
    data = result.get("data") or {}
    for key in ["records", "rows", "list", "items", "dataList"]:
        records = data.get(key)
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    return []


def load_cached_project_list(
    *,
    scene: str = "initiation",
    page_num: int,
    page_size: int,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    candidates: list[tuple[int, float, Path, dict[str, Any], list[dict[str, Any]]]] = []
    for search_dir in api_result_search_dirs(scene):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*_project_list.json"):
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


def load_cached_project_summary(project_id: str, scene: str = "initiation") -> dict[str, Any] | None:
    candidate_records: list[tuple[float, dict[str, Any]]] = []
    for search_dir in api_result_search_dirs(scene):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*_project_list.json"):
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


def load_cached_task_orders_by_project(project_id: str) -> list[dict[str, Any]]:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return []

    latest_records: dict[str, tuple[float, dict[str, Any]]] = {}
    for search_dir in api_result_search_dirs("task_order"):
        if not search_dir.exists():
            continue
        for path in search_dir.rglob("*_task_order_list.json"):
            try:
                payload = read_json(path)
                records = _extract_task_order_list_records(payload)
            except Exception:
                continue
            try:
                modified_time = path.stat().st_mtime
            except Exception:
                modified_time = 0.0
            for item in records:
                normalized = normalize_task_order_summary(item)
                if str(normalized.get("projectId") or "").strip() != normalized_project_id:
                    continue
                cache_key = str(normalized.get("id") or normalized.get("taskOrderNo") or "").strip()
                if not cache_key:
                    continue
                current = latest_records.get(cache_key)
                if current is not None and current[0] >= modified_time:
                    continue
                latest_records[cache_key] = (modified_time, normalized)

    if not latest_records:
        return []

    rows = [item for _, item in sorted(latest_records.values(), key=lambda entry: entry[0], reverse=True)]
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        cache_key = str(item.get("id") or item.get("taskOrderNo") or "").strip()
        if cache_key in seen:
            continue
        seen.add(cache_key)
        deduped.append(item)
    return deduped


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


def load_cached_project_snapshot(project_id: str, scene: str = "initiation") -> dict[str, Any] | None:
    latest_records: dict[str, tuple[float, dict[str, Any]]] = {}
    normalized_project_id = sanitize_file_stem(str(project_id or "").strip())
    for search_dir in api_result_search_dirs(scene):
        project_dir = search_dir / "projects" / normalized_project_id
        if not project_dir.exists():
            continue
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
    normalized["id"] = first_non_empty(
        project.get("id"),
        project.get("projectId"),
        project.get("currentId"),
        project.get("projectEstablishmentId"),
    )
    normalized["projectBudgetId"] = first_non_empty(
        project.get("projectBudgetId"),
        project.get("projectId"),
        normalized.get("projectBudgetId"),
    )
    normalized["projectEstablishmentId"] = first_non_empty(
        project.get("projectEstablishmentId"),
        project.get("establishProjectId"),
        project.get("projectEstablishId"),
        normalized.get("projectEstablishmentId"),
    )
    normalized["projectName"] = first_non_empty(project.get("projectName"), project.get("name"))
    normalized["projectCode"] = first_non_empty(project.get("projectCode"), project.get("serialNo"))
    normalized["domainName"] = first_non_empty(
        project.get("domainName"),
        project.get("belongTeamName"),
        project.get("businessDomainName"),
        project.get("belongAreaName"),
        project.get("belongTeam"),
    )
    normalized["departmentName"] = first_non_empty(
        project.get("departmentName"),
        project.get("belongDepartmentName"),
        project.get("businessDepartmentName"),
        project.get("deptName"),
        project.get("belongDepartment"),
        project.get("businessDepartment"),
    )
    normalized["managerName"] = first_non_empty(
        project.get("projectManagerName"),
        project.get("projectManager"),
        project.get("projectLeaderName"),
        project.get("projectLeader"),
        project.get("managerName"),
    )
    normalized["projectManagerName"] = first_non_empty(
        project.get("projectManagerName"),
        project.get("projectManager"),
        normalized["managerName"],
    )
    normalized["projectLeaderName"] = first_non_empty(project.get("projectLeaderName"), project.get("projectLeader"))
    normalized["projectCategoryName"] = first_non_empty(
        project.get("projectCategoryName"),
        project.get("businessCategoryName"),
        project.get("projectClassifyParentName"),
        project.get("projectFeeTypeName"),
        project.get("projectTypeName"),
        project.get("projectClassifyParent"),
    )
    normalized["projectTypeName"] = first_non_empty(
        project.get("projectTypeName"),
        project.get("businessSubcategoryName"),
        project.get("projectClassifyName"),
        project.get("projectFeeTypeName"),
        project.get("projectCategoryName"),
        project.get("projectClassify"),
    )
    normalized["businessCategoryName"] = first_non_empty(
        project.get("businessCategoryName"),
        project.get("projectClassifyParentName"),
        normalized["projectCategoryName"],
    )
    normalized["businessSubcategoryName"] = first_non_empty(
        project.get("businessSubcategoryName"),
        project.get("projectClassifyName"),
        normalized["projectTypeName"],
    )
    normalized["applyTotalBudget"] = first_non_empty(
        project.get("applyTotalBudget"),
        project.get("applyBudget"),
        project.get("requestBudget"),
        project.get("projectBudget"),
        project.get("proBudget"),
    )
    normalized["applyYearBudget"] = first_non_empty(
        project.get("applyYearBudget"),
        project.get("projectYearBudget"),
        project.get("applyBudgetYear"),
        project.get("proBudgetYear"),
        project.get("yearBudget"),
    )
    normalized["acceptanceAmountTax"] = first_non_empty(
        project.get("acceptanceAmountTax"),
        project.get("acceptMoneyTax"),
        project.get("acceptanceTaxIncludedAmount"),
        project.get("totalAcceptAmountTax"),
        project.get("acceptTotalFeeHasTax"),
    )
    normalized["acceptanceAmount"] = first_non_empty(
        project.get("acceptanceAmount"),
        project.get("acceptMoneyNoTax"),
        project.get("acceptanceWithoutTaxAmount"),
        project.get("totalAcceptAmount"),
        project.get("acceptTotalFeeNoTax"),
    )
    normalized["budgetExecutionRate"] = first_non_empty(
        project.get("budgetExecutionRate"),
        project.get("executeRate"),
        project.get("progressRate"),
        project.get("budgetRate"),
        project.get("budgetProcess"),
    )
    normalized["fixedProject"] = fixed_project
    normalized["fixedProjectLabel"] = "是" if fixed_project is True else "否" if fixed_project is False else "--"
    normalized["projectStatusName"] = first_non_empty(project.get("projectStatusName"), project.get("projectStatus"))
    normalized["flowStatusDisplay"] = first_non_empty(
        project.get("flowStatusName"),
        project.get("flowStatus"),
        project.get("projectFlowStatus"),
    )
    return normalized


def merge_project_summaries(primary: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for key, value in supplement.items():
        current = merged.get(key)
        if current in (None, "") and value not in (None, ""):
            merged[key] = value
    return merged


def normalize_project_param_option(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    label = first_non_empty(
        item.get("label"),
        item.get("name"),
        item.get("paramName"),
        item.get("dictLabel"),
        item.get("text"),
        item.get("value"),
        item.get("paramValue"),
        item.get("dictValue"),
        item.get("code"),
        item.get("id"),
    )
    value = first_non_empty(
        item.get("value"),
        item.get("paramValue"),
        item.get("dictValue"),
        item.get("code"),
        item.get("id"),
        label,
    )
    if not label and not value:
        return None
    return {
        "label": str(label or value or "").strip(),
        "value": str(value or label or "").strip(),
        "name": str(label or value or "").strip(),
        "raw": item,
    }


def extract_project_param_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data")
    candidate_lists: list[Any] = []
    if isinstance(data, list):
        candidate_lists.append(data)
    elif isinstance(data, dict):
        candidate_lists.extend(
            data.get(key)
            for key in ["dataList", "list", "records", "items", "paramList", "rows"]
            if isinstance(data.get(key), list)
        )
    elif isinstance(result.get("rows"), list):
        candidate_lists.append(result.get("rows"))

    for candidate in candidate_lists:
        options = [item for item in (normalize_project_param_option(entry) for entry in candidate) if item]
        if not options:
            continue
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for option in options:
            key = (option["label"], option["value"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(option)
        return deduped
    return []


def extract_classify_table_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for entry in value:
                visit(entry)
            return
        if not isinstance(value, dict):
            return

        marker = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            items.append(value)

        for key in ["children", "childList", "dataList", "list", "rows", "items"]:
            nested = value.get(key)
            if isinstance(nested, (list, dict)):
                visit(nested)

    visit(result.get("data"))
    return items


def extract_project_list_data(result: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    data = result.get("data") or {}
    if isinstance(data, dict):
        records = data.get("dataList")
        if isinstance(records, list):
            return [normalize_project_summary(item) for item in records if isinstance(item, dict)], int(data.get("total", 0) or 0)
        for key in ["records", "rows", "list", "items"]:
            records = data.get(key)
            if isinstance(records, list):
                total = data.get("total")
                if total in (None, ""):
                    total = data.get("count")
                if total in (None, ""):
                    total = len(records)
                return [normalize_project_summary(item) for item in records if isinstance(item, dict)], int(total or 0)
    if isinstance(data, list):
        return [normalize_project_summary(item) for item in data if isinstance(item, dict)], len(data)
    return [], 0


def _extract_list_and_total(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], len(payload)
    if not isinstance(payload, dict):
        return [], 0

    direct_list = payload.get("dataList")
    if isinstance(direct_list, list):
        total = payload.get("total")
        if total in (None, ""):
            total = payload.get("count")
        if total in (None, ""):
            total = len(direct_list)
        return [item for item in direct_list if isinstance(item, dict)], int(total or 0)

    for key in ["records", "rows", "list", "items", "pageList", "resultList"]:
        records = payload.get(key)
        if isinstance(records, list):
            total = payload.get("total")
            if total in (None, ""):
                total = payload.get("count")
            if total in (None, ""):
                total = payload.get("totalCount")
            if total in (None, ""):
                total = payload.get("recordCount")
            if total in (None, ""):
                total = payload.get("totalElements")
            if total in (None, ""):
                total = len(records)
            return [item for item in records if isinstance(item, dict)], int(total or 0)

    for key in ["data", "page", "pageData", "result", "content"]:
        nested = payload.get(key)
        records, total = _extract_list_and_total(nested)
        if records:
            return records, total
    return [], 0


def normalize_task_order_summary(task_order: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(task_order)
    normalized["id"] = first_non_empty(
        task_order.get("id"),
        task_order.get("taskId"),
        task_order.get("taskOrderId"),
        task_order.get("taskInfoId"),
    )
    normalized["projectId"] = first_non_empty(
        task_order.get("projectId"),
        task_order.get("projectBudgetId"),
        task_order.get("projectEstablishmentId"),
        task_order.get("establishProjectId"),
        task_order.get("projectInfoId"),
    )
    normalized["taskOrderNo"] = first_non_empty(
        task_order.get("taskSerialCode"),
        task_order.get("taskOrderNo"),
        task_order.get("taskNo"),
        task_order.get("taskNum"),
        task_order.get("taskOrderCode"),
        task_order.get("serialNo"),
        task_order.get("taskCode"),
        task_order.get("code"),
    )
    normalized["taskOrderName"] = first_non_empty(
        task_order.get("taskOrderName"),
        task_order.get("taskName"),
        task_order.get("name"),
        task_order.get("taskInfoName"),
        task_order.get("taskOrderTitle"),
    )
    normalized["supplierName"] = first_non_empty(
        task_order.get("supplierName"),
        task_order.get("supplier"),
        task_order.get("vendorName"),
        task_order.get("providerName"),
        task_order.get("supplierCompanyName"),
    )
    normalized["projectName"] = first_non_empty(
        task_order.get("projectName"),
        task_order.get("projectInfoName"),
        task_order.get("proName"),
        task_order.get("project"),
    )
    normalized["applyTotalBudget"] = first_non_empty(
        task_order.get("applyTotalBudget"),
        task_order.get("applyBudget"),
        task_order.get("taskApplyTotalBudget"),
        task_order.get("applyAmount"),
        task_order.get("totalBudget"),
    )
    normalized["applyYearBudget"] = first_non_empty(
        task_order.get("applyYearBudget"),
        task_order.get("applyBudgetYear"),
        task_order.get("taskApplyYearBudget"),
        task_order.get("yearBudget"),
        task_order.get("annualBudget"),
    )
    normalized["domainName"] = first_non_empty(
        task_order.get("belongTeamName"),
        task_order.get("domainName"),
        task_order.get("belongDomainName"),
        task_order.get("domain"),
        task_order.get("belongAreaName"),
        task_order.get("fieldName"),
    )
    normalized["startTime"] = first_non_empty(
        task_order.get("planStartTime"),
        task_order.get("startTime"),
        task_order.get("startDate"),
        task_order.get("beginTime"),
        task_order.get("taskStartTime"),
    )
    normalized["endTime"] = first_non_empty(
        task_order.get("planEndTime"),
        task_order.get("endTime"),
        task_order.get("endDate"),
        task_order.get("finishTime"),
    )
    normalized["approvalPassTime"] = first_non_empty(
        task_order.get("taskAduitTime"),
        task_order.get("approvalPassTime"),
        task_order.get("approvalTime"),
        task_order.get("approveTime"),
        task_order.get("passTime"),
        task_order.get("taskApprovePassTime"),
    )
    normalized["amountWarningTime"] = first_non_empty(
        task_order.get("taskEndTime"),
        task_order.get("amountWarningTime"),
        task_order.get("firstWarningTime"),
        task_order.get("firstWarnTime"),
        task_order.get("moneyWarnTime"),
        task_order.get("firstAmountWarningTime"),
    )
    normalized["taskTotalManday"] = first_non_empty(
        task_order.get("taskCostDay"),
        task_order.get("taskTotalManday"),
        task_order.get("taskManday"),
        task_order.get("totalManDay"),
        task_order.get("totalManday"),
        task_order.get("taskDays"),
    )
    normalized["issueAmountTax"] = first_non_empty(
        task_order.get("taskAmountTax"),
        task_order.get("issueAmountTax"),
        task_order.get("assignAmountTax"),
        task_order.get("taskIssueAmountTax"),
        task_order.get("distributionAmountTax"),
        task_order.get("taskTotalFeeHasTax"),
    )
    normalized["issueAmountNoTax"] = first_non_empty(
        task_order.get("taskAmountNoTax"),
        task_order.get("issueAmountNoTax"),
        task_order.get("assignAmountNoTax"),
        task_order.get("taskIssueAmountNoTax"),
        task_order.get("distributionAmountNoTax"),
        task_order.get("taskTotalFeeNoTax"),
    )
    normalized["actualManday"] = first_non_empty(
        task_order.get("actualCostDay"),
        task_order.get("actualManday"),
        task_order.get("realManday"),
        task_order.get("actualManDay"),
        task_order.get("actualDays"),
        task_order.get("usedManday"),
    )
    normalized["acceptanceAmountTax"] = first_non_empty(
        task_order.get("settlementAmount"),
        task_order.get("acceptanceAmountTax"),
        task_order.get("taskAcceptAmountTax"),
        task_order.get("acceptAmountTax"),
        task_order.get("checkAmountTax"),
    )
    normalized["acceptanceAmountNoTax"] = first_non_empty(
        task_order.get("settlementAmountNoTax"),
        task_order.get("acceptanceCosts"),
        task_order.get("acceptanceAmountNoTax"),
        task_order.get("taskAcceptAmountNoTax"),
        task_order.get("acceptAmountNoTax"),
        task_order.get("checkAmountNoTax"),
    )
    normalized["executionRate"] = first_non_empty(
        task_order.get("taskExecuteRate"),
        task_order.get("executionRate"),
        task_order.get("taskExecutionRate"),
        task_order.get("executeRate"),
        task_order.get("runRate"),
        task_order.get("progressRate"),
    )
    normalized["taskOrderStatus"] = first_non_empty(
        task_order.get("taskStatusName"),
        task_order.get("taskStatus"),
        task_order.get("taskOrderStatus"),
        task_order.get("taskOrderStatusName"),
        task_order.get("statusName"),
        task_order.get("status"),
    )
    return normalized


def extract_task_order_list_data(result: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    records, total = _extract_list_and_total(result.get("data"))
    if not records:
        records, total = _extract_list_and_total(result)
    return [normalize_task_order_summary(item) for item in records], total


def build_option_name_map(options: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in options:
        if not isinstance(item, dict):
            continue
        label = str(first_non_empty(item.get("label"), item.get("name"), item.get("value")) or "").strip()
        if not label:
            continue
        for raw_key in [item.get("value"), item.get("id"), item.get("name"), item.get("label")]:
            key = str(raw_key or "").strip()
            if key:
                mapping[key] = label
    return mapping


def normalize_supplier_option(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    label = first_non_empty(
        item.get("supplierName"),
        item.get("name"),
        item.get("label"),
        item.get("companyName"),
        item.get("fullName"),
        item.get("supplierMain"),
    )
    value = first_non_empty(
        item.get("supplierName"),
        item.get("name"),
        item.get("label"),
        item.get("companyName"),
        item.get("fullName"),
        item.get("supplierMain"),
        item.get("supplierId"),
        item.get("id"),
        item.get("value"),
        item.get("code"),
    )
    if not label and not value:
        return None
    return {
        "label": str(label or value or "").strip(),
        "value": str(value or label or "").strip(),
        "name": str(label or value or "").strip(),
        "raw": item,
    }


def extract_supplier_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data")
    candidate_lists: list[Any] = []
    if isinstance(data, list):
        candidate_lists.append(data)
    elif isinstance(data, dict):
        candidate_lists.extend(
            data.get(key)
            for key in ["dataList", "list", "records", "items", "rows", "supplierList"]
            if isinstance(data.get(key), list)
        )
    elif isinstance(result.get("rows"), list):
        candidate_lists.append(result.get("rows"))

    for candidate in candidate_lists:
        options = [item for item in (normalize_supplier_option(entry) for entry in candidate) if item]
        if not options:
            continue
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for option in options:
            key = (option["label"], option["value"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(option)
        return deduped
    return []


def apply_task_order_param_labels(task_order: dict[str, Any], *, status_map: dict[str, str]) -> dict[str, Any]:
    normalized = dict(task_order)
    raw_status = str(first_non_empty(task_order.get("taskStatus"), task_order.get("taskOrderStatus"), task_order.get("status")) or "").strip()
    if raw_status and raw_status in status_map:
        normalized["taskStatusName"] = status_map[raw_status]
        normalized["taskOrderStatusName"] = status_map[raw_status]
        normalized["taskOrderStatus"] = status_map[raw_status]
    return normalized


def apply_acceptance_param_labels(
    project: dict[str, Any],
    *,
    category_map: dict[str, str],
    subcategory_map: dict[str, str],
    status_map: dict[str, str],
) -> dict[str, Any]:
    normalized = dict(project)
    category_code = str(first_non_empty(project.get("projectClassifyParent"), project.get("businessCategoryCode")) or "").strip()
    subcategory_code = str(first_non_empty(project.get("projectClassify"), project.get("businessSubcategoryCode")) or "").strip()
    status_code = str(first_non_empty(project.get("projectStatus"), project.get("projectStatusCode")) or "").strip()

    category_name = category_map.get(category_code) or category_map.get(str(project.get("businessCategoryName") or "").strip())
    subcategory_name = subcategory_map.get(subcategory_code) or subcategory_map.get(str(project.get("businessSubcategoryName") or "").strip())
    status_name = status_map.get(status_code) or status_map.get(str(project.get("projectStatusName") or "").strip())

    if category_name:
        normalized["businessCategoryName"] = category_name
        normalized["projectCategoryName"] = category_name
    if subcategory_name:
        normalized["businessSubcategoryName"] = subcategory_name
        normalized["projectTypeName"] = subcategory_name
    if status_name:
        normalized["projectStatusName"] = status_name
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

def matches_task_order_filters(task_order: dict[str, Any], filters: dict[str, Any] | None = None) -> bool:
    if not filters:
        return True
    text_filters = {
        "task_order_no": [task_order.get("taskOrderNo"), task_order.get("taskSerialCode"), task_order.get("taskNo"), task_order.get("taskCode")],
        "task_order_name": [task_order.get("taskOrderName"), task_order.get("taskName"), task_order.get("name")],
        "supplier": [task_order.get("supplierName"), task_order.get("supplier"), task_order.get("vendorName")],
        "project_name": [task_order.get("projectName"), task_order.get("projectInfoName")],
        "domain": [task_order.get("domainName"), task_order.get("belongTeamName"), task_order.get("belongDomainName"), task_order.get("domain")],
        "task_order_status": [
            task_order.get("taskOrderStatus"),
            task_order.get("taskOrderStatusName"),
            task_order.get("statusName"),
            task_order.get("taskStatus"),
            task_order.get("taskStatusName"),
        ],
    }
    for key, candidates in text_filters.items():
        expected = str(filters.get(key, "") or "").strip()
        if expected and not any(_match_text(candidate, expected) for candidate in candidates):
            return False
    return True


def integration_env_defaults() -> dict[str, Any]:
    base_url = os.getenv(
        "PROJECT_APPROVAL_IWORK_BASE_URL",
        "https://prod-itpm.faw.cn/itpmNew/gateway/sop-itpm-service",
    )
    task_order_base_url = os.getenv(
        "PROJECT_APPROVAL_IWORK_TASK_ORDER_BASE_URL",
        "https://prod-itpm.faw.cn/itpmNew/gateway/sop-itpm-taskorder",
    )
    resourcepool_base_url = os.getenv(
        "PROJECT_APPROVAL_IWORK_RESOURCEPOOL_BASE_URL",
        "https://prod-itpm.faw.cn/itpmNew/gateway/resourcepool",
    )
    iam_url = os.getenv(
        "PROJECT_APPROVAL_IWORK_IAM_URL",
        "https://iwork.faw.cn/api-dev/dcp-base-sso/iamToken",
    )
    return {
        "base_url": base_url,
        "task_order_base_url": task_order_base_url,
        "resourcepool_base_url": resourcepool_base_url,
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
        self.task_order_base_url = str(config.get("task_order_base_url") or "").rstrip("/") or self.base_url
        self.resourcepool_base_url = str(config.get("resourcepool_base_url") or "").rstrip("/") or self.base_url
        self.timeout = int(config.get("timeout", 20))
        self.verify_ssl = bool(config.get("verify_ssl", True))
        self.ca_bundle_path = str(config.get("ca_bundle_path", "") or "").strip()
        self.verify_option: bool | str = self._resolve_verify_option()
        self.session = requests.Session()
        self.session.trust_env = False
        if self.verify_option is False:
            urllib3.disable_warnings(InsecureRequestWarning)

    def task_order_list_url(self) -> str:
        return f"{self.task_order_base_url}/taskInfo/queryNewTaskListPage"

    def supplier_main_url(self) -> str:
        return f"{self.resourcepool_base_url}/talentInfo/getSupplierMain"

    def task_order_url(self, path: str) -> str:
        normalized_path = str(path or "").strip()
        if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
            return normalized_path
        return f"{self.task_order_base_url}{normalized_path}"

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
        scene: str = "initiation",
        project_id: str | None = None,
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        effective_api_name = api_name or path
        resolved_project_id = infer_project_id(path, payload=payload, explicit_project_id=project_id)
        started_at = time.perf_counter()
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
                scene=scene,
                project_id=resolved_project_id,
                result=result,
            )
            if strict and isinstance(result, dict):
                code = result.get("code")
                if code not in (None, 0):
                    raise RemoteAPIError(code=code, message=str(result.get("message") or "远程接口调用失败"), payload=result)
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            LOGGER.info(
                "timing remote_api api=%s method=%s status=%s elapsed_ms=%s project_id=%s",
                effective_api_name,
                method.upper(),
                response.status_code,
                elapsed_ms,
                resolved_project_id or "-",
            )
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
                scene=scene,
                project_id=resolved_project_id,
                result=result_payload,
                error=str(exc),
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            LOGGER.warning(
                "timing remote_api_failed api=%s method=%s status=%s elapsed_ms=%s project_id=%s error=%s",
                effective_api_name,
                method.upper(),
                getattr(response, "status_code", "error"),
                elapsed_ms,
                resolved_project_id or "-",
                exc,
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
        scene: str = "initiation",
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
                scene=scene,
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
                scene=scene,
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
        scene: str = "initiation",
        page_num: int = 1,
        page_size: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"pageNum": page_num, "pageSize": page_size}
        if filters:
            payload.update(filters)
        normalized_scene = normalize_scene(scene)
        try:
            if normalized_scene == "acceptance":
                category_map = build_option_name_map(self.safe_list_project_params(26))
                subcategory_map = build_option_name_map(self.safe_list_project_params(4))
                status_map = build_option_name_map(self.safe_list_project_params(71))
                total_result = self.request_json(
                    "POST",
                    "/projectEstablishment/queryProjectEstablishmentListByParam",
                    payload=payload,
                    strict=True,
                    scene=normalized_scene,
                    api_name="acceptance_project_total",
                )
                total_projects, total = extract_project_list_data(total_result)
                try:
                    page_query = {
                        "currentPage": page_num,
                        "pageSize": page_size,
                        "pageNum": page_num,
                    }
                    if filters:
                        page_query.update({key: value for key, value in filters.items() if value not in (None, "")})
                    page_path = f"/projectAccept?{urllib.parse.urlencode(page_query)}"
                    page_result = self.request_json(
                        "GET",
                        page_path,
                        strict=True,
                        scene=normalized_scene,
                        api_name="acceptance_project_list",
                    )
                    page_projects, page_total = extract_project_list_data(page_result)
                    total_project_map: dict[str, dict[str, Any]] = {}
                    for item in total_projects:
                        project_key = str(first_non_empty(item.get("id"), item.get("projectCode"), item.get("projectName")) or "").strip()
                        if project_key:
                            total_project_map[project_key] = item
                    merged_page_projects: list[dict[str, Any]] = []
                    for item in page_projects:
                        project_key = str(first_non_empty(item.get("id"), item.get("projectCode"), item.get("projectName")) or "").strip()
                        supplement = total_project_map.get(project_key)
                        merged = merge_project_summaries(item, supplement) if supplement else item
                        merged_page_projects.append(
                            apply_acceptance_param_labels(
                                merged,
                                category_map=category_map,
                                subcategory_map=subcategory_map,
                                status_map=status_map,
                            )
                        )
                    return {
                        "raw": page_result,
                        "raw_total": total_result,
                        "projects": merged_page_projects,
                        "total": total or page_total,
                        "code": page_result.get("code"),
                        "message": page_result.get("message"),
                        "source": "remote",
                        "warning": "",
                        "scene": normalized_scene,
                        "page_source": "projectAccept",
                        "total_source": "projectEstablishment",
                    }
                except Exception:
                    return {
                        "raw": total_result,
                        "projects": [
                            apply_acceptance_param_labels(
                                item,
                                category_map=category_map,
                                subcategory_map=subcategory_map,
                                status_map=status_map,
                            )
                            for item in total_projects
                        ],
                        "total": total,
                        "code": total_result.get("code"),
                        "message": total_result.get("message"),
                        "source": "remote",
                        "warning": "projectAccept 接口调用失败，当前页内容回退到原始列表接口。",
                        "scene": normalized_scene,
                        "page_source": "projectEstablishment",
                        "total_source": "projectEstablishment",
                    }

            result = self.request_json(
                "POST",
                "/projectEstablishment/queryProjectEstablishmentList",
                payload=payload,
                strict=True,
                scene=normalized_scene,
                api_name="project_list",
            )
            projects, total = extract_project_list_data(result)
            return {
                "raw": result,
                "projects": projects,
                "total": total,
                "code": result.get("code"),
                "message": result.get("message"),
                "source": "remote",
                "warning": "",
                "scene": normalized_scene,
            }
        except Exception:
            cached = load_cached_project_list(scene=normalized_scene, page_num=page_num, page_size=page_size, filters=filters)
            if cached is not None:
                return cached
            raise

    def list_task_orders(
        self,
        *,
        page_num: int = 1,
        page_size: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "currentPage": page_num,
            "pageSize": page_size,
        }
        if filters:
            payload.update({key: value for key, value in filters.items() if value not in (None, "")})
        result = self.request_json(
            "POST",
            self.task_order_list_url(),
            payload=payload,
            strict=False,
            scene="task_order",
            api_name="task_order_list",
        )
        code = result.get("code")
        if code not in (None, 0, "0", 200, "200"):
            raise RemoteAPIError(code=code, message=str(result.get("message") or "任务单列表接口调用失败"), payload=result)
        task_orders, total = extract_task_order_list_data(result)
        status_map = build_option_name_map(self.safe_list_task_order_status_options())
        if status_map:
            task_orders = [apply_task_order_param_labels(item, status_map=status_map) for item in task_orders]
        return {
            "raw": result,
            "projects": task_orders,
            "total": total,
            "code": result.get("code"),
            "message": result.get("message"),
            "source": "remote",
            "warning": "",
            "scene": "task_order",
        }

    def list_task_orders_by_project(self, project_id: str, *, page_size: int = 200) -> list[dict[str, Any]]:
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return []

        try:
            first_page = self.list_task_orders(page_num=1, page_size=page_size)
            total = int(first_page.get("total") or len(first_page.get("projects") or []))
            all_rows = list(first_page.get("projects") or [])
            total_pages = max(1, (total + page_size - 1) // page_size)
            for page_num in range(2, total_pages + 1):
                page_result = self.list_task_orders(page_num=page_num, page_size=page_size)
                all_rows.extend(page_result.get("projects") or [])
            return [item for item in all_rows if str(item.get("projectId") or "").strip() == normalized_project_id]
        except Exception:
            return load_cached_task_orders_by_project(normalized_project_id)

    def list_acceptance_review_projects(
        self,
        *,
        status_codes: list[str] | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        normalized_status_codes = [str(code or "").strip() for code in (status_codes or ["4", "9"]) if str(code or "").strip()]
        cached_payload = load_cached_acceptance_review_projects(normalized_status_codes)
        if cached_payload is not None:
            cached_payload["warning"] = str(cached_payload.get("warning") or "")
            cached_payload["scene"] = "acceptance"
            return cached_payload
        try:
            category_map = build_option_name_map(self.safe_list_project_params(26))
            subcategory_map = build_option_name_map(self.safe_list_project_params(4))
            status_map = build_option_name_map(self.safe_list_project_params(71))
            items: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            raw_pages: list[dict[str, Any]] = []

            for status_code in normalized_status_codes:
                page_num = 1
                while True:
                    page_query = {
                        "projectStatus": status_code,
                        "currentPage": page_num,
                        "pageSize": page_size,
                        "pageNum": page_num,
                    }
                    page_path = f"/projectAccept?{urllib.parse.urlencode(page_query)}"
                    page_result = self.request_json(
                        "GET",
                        page_path,
                        strict=True,
                        scene="acceptance",
                        api_name=f"acceptance_review_project_list_{status_code}",
                    )
                    raw_pages.append(page_result)
                    page_projects, total = extract_project_list_data(page_result)
                    for item in page_projects:
                        normalized = apply_acceptance_param_labels(
                            item,
                            category_map=category_map,
                            subcategory_map=subcategory_map,
                            status_map=status_map,
                        )
                        project_id = str(first_non_empty(normalized.get("id"), normalized.get("projectCode"), normalized.get("projectName")) or "").strip()
                        if project_id and project_id in seen_ids:
                            continue
                        if project_id:
                            seen_ids.add(project_id)
                        items.append(normalized)
                    if not page_projects or len(page_projects) < page_size or len(page_projects) * page_num >= total:
                        break
                    page_num += 1

            result_payload = {
                "projects": items,
                "total": len(items),
                "status_codes": normalized_status_codes,
                "raw_pages": raw_pages,
                "source": "remote",
                "warning": "",
                "scene": "acceptance",
            }
            store_acceptance_review_projects_cache(normalized_status_codes, result_payload)
            return result_payload
        except Exception:
            stale_payload = load_cached_acceptance_review_projects(normalized_status_codes, allow_stale=True)
            if stale_payload is not None:
                stale_payload["warning"] = "Remote acceptance review list failed; showing the latest cached result."
                stale_payload["scene"] = "acceptance"
                return stale_payload
            raise

    def fetch_task_order_detail(self, task_order_id: str, project_id: str = "") -> dict[str, Any]:
        normalized_task_order_id = str(task_order_id or "").strip()
        normalized_project_id = str(project_id or "").strip()
        if not normalized_task_order_id:
            raise ValueError("缺少任务单ID")

        def safe_request(key: str, method: str, path: str, *, payload: dict[str, Any] | None = None) -> Any:
            try:
                result = self.request_json(
                    method,
                    self.task_order_url(path),
                    payload=payload,
                    strict=False,
                    scene="task_order",
                    api_name=key,
                    project_id=normalized_task_order_id,
                )
                if isinstance(result, dict) and "data" in result:
                    return result.get("data")
                return result
            except Exception as exc:
                errors[key] = str(exc)
                return None

        errors: dict[str, str] = {}

        def extract_project_id(value: Any) -> str:
            records, _ = _extract_list_and_total(value)
            if not records and isinstance(value, dict):
                records = [value]
            for row in records:
                if not isinstance(row, dict):
                    continue
                candidate = str(
                    first_non_empty(
                        row.get("projectId"),
                        row.get("projectBudgetId"),
                        row.get("projectInfoId"),
                        row.get("projectEstablishmentId"),
                        row.get("establishProjectId"),
                    )
                    or ""
                ).strip()
                if candidate:
                    return candidate
            return ""
        base_detail = safe_request(
            "task_order_base_detail",
            "POST",
            "/taskOrderInfo/getTaskBaseDetail",
            payload={"id": normalized_task_order_id},
        )
        business_units = safe_request(
            "task_order_business_units",
            "POST",
            "/businessUnit/queryTasklistBusinessUnit",
            payload={"taskId": normalized_task_order_id},
        )
        approval_nodes = safe_request(
            "task_order_approval_nodes",
            "POST",
            "/approvalNode/queryTasklistApprovalNode",
            payload={"taskId": normalized_task_order_id},
        )
        process_rows = safe_request(
            "task_order_process_rows",
            "POST",
            "/taskOrderInfo/getRightProcessList",
            payload={"taskId": normalized_task_order_id},
        )
        matrix_rows = safe_request(
            "task_order_matrix_rows",
            "GET",
            f"/taskInfo/getProjectTaskMatrixList/{urllib.parse.quote(normalized_task_order_id)}",
        )
        if not _extract_list_and_total(matrix_rows)[0]:
            legacy_matrix_rows = safe_request(
                "task_order_matrix_rows_legacy",
                "POST",
                f"{self.base_url}/tblProjectTaskPerson/list",
                payload={"taskId": normalized_task_order_id},
            )
            if _extract_list_and_total(legacy_matrix_rows)[0]:
                matrix_rows = legacy_matrix_rows
        resolved_project_id = normalized_project_id or extract_project_id(base_detail)
        history_rows = (
            safe_request(
                "task_order_history_rows",
                "GET",
                f"/taskInfo/getHistoryTaskList/{urllib.parse.quote(resolved_project_id)}",
            )
            if resolved_project_id
            else []
        )
        spec_rows = safe_request(
            "task_order_spec_rows",
            "GET",
            f"/taskOrderInfo/getSpecInfo/{urllib.parse.quote(normalized_task_order_id)}",
        )
        return {
            "taskOrderId": normalized_task_order_id,
            "projectId": resolved_project_id,
            "base_detail": base_detail,
            "business_units": business_units,
            "approval_nodes": approval_nodes,
            "process_rows": process_rows,
            "matrix_rows": matrix_rows,
            "history_rows": history_rows,
            "spec_rows": spec_rows,
            "errors": errors,
        }

    def fetch_contract_detail(self, contract_id: str, contract_number: str = "") -> dict[str, Any]:
        normalized_contract_id = str(contract_id or "").strip()
        normalized_contract_number = str(contract_number or "").strip()
        if normalized_contract_number and normalized_contract_id == normalized_contract_number:
            normalized_contract_id = ""
        if not normalized_contract_id and not normalized_contract_number:
            raise ValueError("缂哄皯鍚堝悓ID")
        result = self.request_json(
            "POST",
            "/contractBasic/detail",
            payload={
                "contractId": normalized_contract_id,
                "contractNumber": normalized_contract_number,
            },
            strict=False,
            scene="acceptance",
            api_name="contract_basic_detail",
            project_id=normalized_contract_id or normalized_contract_number,
        )
        data = result.get("data")
        return data if isinstance(data, dict) else result

    def list_project_statuses(self) -> list[dict[str, Any]]:
        result = self.request_json(
            "GET",
            "/projectCenter/queryProjectStatusList",
            strict=True,
            scene="initiation",
            api_name="project_status_options",
        )
        data = result.get("data") or {}
        return data.get("statusList") or []

    def list_project_params(self, query_type: int) -> list[dict[str, Any]]:
        normalized_query_type = int(query_type)
        result = self.request_json(
            "POST",
            f"/common/projectParam?queryType={normalized_query_type}",
            payload={},
            strict=True,
            scene="acceptance",
            api_name=f"project_param_{normalized_query_type}",
        )
        return extract_project_param_items(result)

    def safe_list_project_params(self, query_type: int) -> list[dict[str, Any]]:
        normalized_query_type = int(query_type)
        ttl_seconds = project_param_cache_ttl_seconds()
        now = time.monotonic()
        if ttl_seconds > 0:
            with _PROJECT_PARAM_CACHE_LOCK:
                cached = _PROJECT_PARAM_CACHE.get(normalized_query_type)
                if cached and float(cached.get("expires_at") or 0) > now:
                    payload = cached.get("items")
                    if isinstance(payload, list):
                        return deepcopy(payload)
                if cached:
                    _PROJECT_PARAM_CACHE.pop(normalized_query_type, None)
        try:
            items = self.list_project_params(normalized_query_type)
        except Exception:
            return []
        if ttl_seconds > 0:
            with _PROJECT_PARAM_CACHE_LOCK:
                _PROJECT_PARAM_CACHE[normalized_query_type] = {
                    "expires_at": now + ttl_seconds,
                    "items": deepcopy(items),
                }
        return items

    def list_task_order_status_options(self) -> list[dict[str, Any]]:
        result = self.request_json(
            "POST",
            "/common/projectParam",
            payload={"queryType": 62},
            strict=True,
            scene="task_order",
            api_name="task_order_status_options",
        )
        return extract_project_param_items(result)

    def safe_list_task_order_status_options(self) -> list[dict[str, Any]]:
        ttl_seconds = project_param_cache_ttl_seconds()
        now = time.monotonic()
        if ttl_seconds > 0:
            with _TASK_ORDER_STATUS_CACHE_LOCK:
                cached = _TASK_ORDER_STATUS_CACHE
                if cached and float(cached.get("expires_at") or 0) > now:
                    payload = cached.get("items")
                    if isinstance(payload, list):
                        return deepcopy(payload)
                if cached:
                    _TASK_ORDER_STATUS_CACHE.clear()
        try:
            items = self.list_task_order_status_options()
        except Exception:
            return []
        if ttl_seconds > 0:
            with _TASK_ORDER_STATUS_CACHE_LOCK:
                _TASK_ORDER_STATUS_CACHE.update(
                    {
                        "expires_at": now + ttl_seconds,
                        "items": deepcopy(items),
                    }
                )
        return items

    def get_project_base_info(self, project_id: str, *, scene: str = "initiation") -> dict[str, Any]:
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return {}
        result = self.request_json(
            "POST",
            "/projectBaseInfo/info",
            payload={"projectId": normalized_project_id},
            strict=False,
            scene=scene,
            api_name="project_base_info",
            project_id=normalized_project_id,
        )
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def list_acceptance_ui_tabs(self, param_code: str) -> list[dict[str, Any]]:
        normalized_param_code = str(param_code or "").strip()
        if not normalized_param_code:
            return []
        result = self.request_json(
            "GET",
            f"/classifyTable/bcList/4/{urllib.parse.quote(normalized_param_code)}",
            strict=False,
            scene="acceptance",
            api_name="acceptance_ui_tabs",
        )
        return extract_classify_table_items(result)

    def list_suppliers(self) -> list[dict[str, Any]]:
        attempts = [
            ("POST", self.supplier_main_url(), None),
            ("POST", self.supplier_main_url(), {}),
            ("GET", self.supplier_main_url(), None),
        ]
        last_error: Exception | None = None
        for method, path, payload in attempts:
            try:
                result = self.request_json(
                    method,
                    path,
                    payload=payload,
                    strict=False,
                    scene="task_order",
                    api_name="task_order_supplier_options",
                )
                options = extract_supplier_items(result)
                if options:
                    return options
            except Exception as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        return []

    def fetch_acceptance_info_list(self, project_id: str) -> list[dict[str, Any]]:
        result = self.request_json(
            "GET",
            f"/acceptDetail/acceptInfoList?projectId={urllib.parse.quote(str(project_id or '').strip())}",
            strict=True,
            scene="acceptance",
            api_name="acceptance_info_list",
            project_id=project_id,
        )
        data = result.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ["dataList", "list", "records", "items", "rows"]:
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def resolve_acceptance_project_ids(self, project_id: str) -> dict[str, str]:
        budget_project_id = str(project_id or "").strip()
        establishment_project_id = ""

        acceptance_summary = load_cached_project_summary(budget_project_id, scene="acceptance") or {}
        establishment_project_id = extract_establishment_project_id(acceptance_summary)

        if not establishment_project_id:
            for search_dir in api_result_search_dirs("initiation"):
                if not search_dir.exists():
                    continue
                for path in search_dir.rglob("*_project_list.json"):
                    try:
                        payload = read_json(path)
                        records = _extract_project_list_records(payload)
                    except Exception:
                        continue
                    for item in records:
                        if str(item.get("projectBudgetId") or "").strip() == budget_project_id:
                            establishment_project_id = str(item.get("id") or "").strip()
                            if establishment_project_id:
                                break
                    if establishment_project_id:
                        break
                if establishment_project_id:
                    break

        if not establishment_project_id:
            try:
                info_list = self.fetch_acceptance_info_list(budget_project_id)
            except Exception:
                info_list = []
            establishment_project_id = extract_establishment_project_id(info_list)

        return {
            "budget_project_id": budget_project_id,
            "establishment_project_id": establishment_project_id or budget_project_id,
        }

    def fetch_project_snapshot(
        self,
        project_id: str,
        *,
        scene: str = "initiation",
        force_refresh: bool = False,
        category: str = "",
    ) -> dict[str, Any]:
        normalized_scene = normalize_scene(scene)
        cache_key = f"{normalized_scene}:{str(project_id or '').strip()}:review-v2"
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
        if normalized_scene == "acceptance":
            resolved_ids = self.resolve_acceptance_project_ids(project_id)
            acceptance_summary = load_cached_project_summary(resolved_ids["budget_project_id"], scene="acceptance") or {}
            resolved_category = first_non_empty(
                category,
                acceptance_summary.get("businessSubcategoryName"),
                acceptance_summary.get("projectClassifyName"),
                acceptance_summary.get("projectTypeName"),
            )
            resolved_serial_no = first_non_empty(
                acceptance_summary.get("projectCode"),
                acceptance_summary.get("serialNo"),
            )
            snapshot["budget_project_id"] = resolved_ids["budget_project_id"]
            snapshot["establishment_project_id"] = resolved_ids["establishment_project_id"]
            endpoints = build_acceptance_snapshot_requests(
                budget_project_id=resolved_ids["budget_project_id"],
                establishment_project_id=resolved_ids["establishment_project_id"],
                category=str(resolved_category or ""),
                serial_no=str(resolved_serial_no or ""),
            )
        else:
            project_summary = load_cached_project_summary(project_id, scene=normalized_scene) or {}
            resolved_category = first_non_empty(
                category,
                project_summary.get("businessSubcategoryName"),
                project_summary.get("projectClassifyName"),
                project_summary.get("projectTypeName"),
            )
            resolved_serial_no = first_non_empty(
                project_summary.get("projectCode"),
                project_summary.get("serialNo"),
            )
            endpoints = build_project_snapshot_requests(
                project_id,
                scene=normalized_scene,
                category=str(resolved_category or ""),
                serial_no=str(resolved_serial_no or ""),
            )
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
                    scene=normalized_scene,
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

        if normalized_scene == "acceptance":
            budget_project_id = str(snapshot.get("budget_project_id") or project_id).strip() or str(project_id)
            accept_ids = collect_accept_ids(endpoint_results)
            if accept_ids:
                detail_requests = []
                for accept_id in accept_ids[:3]:
                    detail_requests.extend(build_acceptance_detail_requests(budget_project_id, accept_id))
                detail_results: dict[str, dict[str, Any]] = {}
                detail_workers = max(2, min(max_workers, len(detail_requests)))
                with futures.ThreadPoolExecutor(max_workers=detail_workers) as executor:
                    detail_future_map = {executor.submit(run_endpoint, endpoint): endpoint["name"] for endpoint in detail_requests}
                    for future in futures.as_completed(detail_future_map):
                        endpoint_name = detail_future_map[future]
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
                        detail_results[name] = payload
                aggregate_acceptance_detail_results(detail_results, endpoint_results)
                for endpoint_name in [
                    "acceptance_task_info",
                    "acceptance_contract_info",
                    "acceptance_stage_tasks",
                    "acceptance_stage_contracts",
                    "acceptance_count_data",
                    "acceptance_architecture_elements",
                ]:
                    if endpoint_name in endpoint_results:
                        snapshot["endpoints"][endpoint_name] = endpoint_results[endpoint_name]

        if cache_key and ttl_seconds > 0:
            with _SNAPSHOT_CACHE_LOCK:
                _SNAPSHOT_CACHE[cache_key] = {
                    "expires_at": time.monotonic() + ttl_seconds,
                    "snapshot": deepcopy(snapshot),
                }
        return snapshot
