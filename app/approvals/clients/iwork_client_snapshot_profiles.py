from __future__ import annotations

import urllib.parse
from typing import Any

from app.core.config.scenes import normalize_scene


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def normalize_category_token(value: Any) -> str:
    return "".join(char for char in str(value or "").strip() if char.isalnum())


def _project_id_payload(project_id: str, serial_no: str) -> dict[str, Any]:
    return {"projectId": project_id}


def _project_id_with_data_type_payload(project_id: str, serial_no: str) -> dict[str, Any]:
    return {"projectId": project_id, "dataType": 1}


def _serial_no_payload(project_id: str, serial_no: str) -> dict[str, Any]:
    if str(serial_no or "").strip():
        return {"serialNo": serial_no}
    return {"projectId": project_id}


SNAPSHOT_REVIEW_PROFILES: dict[str, dict[str, Any]] = {
    normalize_category_token("系统开发及实施"): {
        "include_project_goal": True,
        "requests": [
            ("project_scope_dev", "POST", "/projectBaseInfo/eamapAndSystem", _project_id_payload),
            ("system_scope_okr", "POST", "/projectBaseInfo/eamapAndSystemOkr", _project_id_payload),
            ("system_scope", "POST", "/projectMicosInfo/getList", _project_id_with_data_type_payload),
        ],
    },
    normalize_category_token("系统产品购买"): {
        "include_project_goal": True,
        "requests": [
            ("project_scope_dev", "POST", "/projectBaseInfo/eamapAndSystem", _project_id_payload),
            ("system_scope_okr", "POST", "/projectBaseInfo/eamapAndSystemOkr", _project_id_payload),
            ("system_scope", "POST", "/projectMicosInfo/getList", _project_id_with_data_type_payload),
        ],
    },
    normalize_category_token("产品运营"): {
        "include_project_goal": True,
        "requests": [
            ("project_scope_dev", "POST", "/projectBaseInfo/eamapAndSystem", _project_id_payload),
            ("system_scope_okr", "POST", "/projectBaseInfo/eamapAndSystemOkr", _project_id_payload),
            ("system_scope", "POST", "/projectMicosInfo/getList", _project_id_with_data_type_payload),
        ],
    },
    normalize_category_token("系统运维(一、二线)"): {
        "requests": [
            ("project_scope_line", "POST", "/projectBaseInfo/getProjectScopeLine", _serial_no_payload),
            ("project_scope_expense_detail", "POST", "/projectBasic/queryProjectExpenseDetail", _serial_no_payload),
        ],
    },
    normalize_category_token("数据中心维护"): {
        "requests": [
            ("project_scope_expense_detail", "POST", "/projectBasic/queryProjectExpenseDetail", _serial_no_payload),
            ("project_scope_expense", "POST", "/projectBasic/queryProjectExpense", _serial_no_payload),
            ("project_scope_ops_legacy", "POST", "/projectBaseInfo/projectRange/list", _project_id_payload),
        ],
    },
    normalize_category_token("系统运维(三线)"): {
        "requests": [
            ("project_scope_ops_get_scope", "POST", "/projectBaseInfo/getProjectScope", _serial_no_payload),
        ],
    },
    normalize_category_token("系统运维(产品维保)"): {
        "requests": [
            ("project_scope_purchase_items", "POST", "/tblPurchaseItems/list", _project_id_payload),
        ],
    },
    normalize_category_token("基础服务"): {
        "requests": [
            ("project_scope_ops_legacy", "POST", "/projectBaseInfo/projectRange/list", _project_id_payload),
        ],
    },
    normalize_category_token("数据服务"): {
        "requests": [
            ("project_scope_ops_legacy", "POST", "/projectBaseInfo/projectRange/list", _project_id_payload),
        ],
    },
    normalize_category_token("安全服务"): {
        "requests": [
            ("project_scope_security_data", "POST", "/security/getData", _project_id_payload),
            ("project_scope_security_list", "POST", "/security/list", _project_id_payload),
        ],
    },
    normalize_category_token("保密服务"): {
        "requests": [
            ("project_scope_ops_legacy", "POST", "/projectBaseInfo/projectRange/list", _project_id_payload),
        ],
    },
    normalize_category_token("数据订阅及购买"): {
        "requests": [
            ("project_scope_ops", "POST", "/project/range/list", _project_id_payload),
        ],
    },
    normalize_category_token("研发工具订阅许可升级"): {
        "requests": [
            ("project_scope_ops", "POST", "/project/range/list", _project_id_payload),
        ],
    },
    normalize_category_token("研发工具许可购买"): {
        "requests": [
            ("project_scope_ops", "POST", "/project/range/list", _project_id_payload),
        ],
    },
    normalize_category_token("非研发工具订阅许可升级"): {
        "requests": [
            ("project_scope_ops", "POST", "/project/range/list", _project_id_payload),
        ],
    },
    normalize_category_token("非研发工具许可购买"): {
        "requests": [
            ("project_scope_ops", "POST", "/project/range/list", _project_id_payload),
        ],
    },
    normalize_category_token("设备购买及弱电布线"): {
        "requests": [
            ("project_scope_machine", "POST", "/projectBaseInfo/getMachineInfo", _project_id_payload),
        ],
    },
    normalize_category_token("机房建设"): {
        "requests": [],
    },
    normalize_category_token("设备维修"): {
        "requests": [
            ("project_scope_bus_add", "POST", "/busEquipmentAdd/queryAdd", _project_id_payload),
            ("project_scope_bus_maintain", "POST", "/busEquipmentAdd/queryMaintain", _project_id_payload),
        ],
    },
    normalize_category_token("资源租赁"): {
        "requests": [
            ("project_scope_ops_legacy", "POST", "/projectBaseInfo/projectRange/list", _project_id_payload),
        ],
    },
}


def _build_snapshot_request(name: str, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    return {"name": name, "method": method, "path": path, "payload": payload}


def build_default_review_requests(project_id: str) -> list[dict[str, Any]]:
    return [
        _build_snapshot_request("project_goal", "GET", f"/project/goal/get/{project_id}", None),
        _build_snapshot_request("project_scope_dev", "POST", "/projectBaseInfo/eamapAndSystem", {"projectId": project_id}),
        _build_snapshot_request("project_scope_ops", "POST", "/project/range/list", {"projectId": project_id}),
        _build_snapshot_request("project_scope_ops_get_scope", "POST", "/projectBaseInfo/getProjectScope", {"projectId": project_id}),
        _build_snapshot_request("project_scope_ops_legacy", "POST", "/projectBaseInfo/projectRange/list", {"projectId": project_id}),
        _build_snapshot_request("system_scope_okr", "POST", "/projectBaseInfo/eamapAndSystemOkr", {"projectId": project_id}),
        _build_snapshot_request("system_scope", "POST", "/projectMicosInfo/getList", {"projectId": project_id, "dataType": 1}),
    ]


def resolve_snapshot_review_profile(category: str | None = None) -> dict[str, Any] | None:
    normalized_key = normalize_category_token(category)
    if not normalized_key:
        return None
    return SNAPSHOT_REVIEW_PROFILES.get(normalized_key)


def build_category_review_requests(project_id: str, *, category: str = "", serial_no: str = "") -> list[dict[str, Any]]:
    profile = resolve_snapshot_review_profile(category)
    if not profile:
        return build_default_review_requests(project_id)

    requests: list[dict[str, Any]] = [
        _build_snapshot_request("project_scope_dev", "POST", "/projectBaseInfo/eamapAndSystem", {"projectId": project_id}),
    ]
    seen_names = {"project_scope_dev"}
    if profile.get("include_project_goal"):
        requests.append(_build_snapshot_request("project_goal", "GET", f"/project/goal/get/{project_id}", None))
        seen_names.add("project_goal")
    for name, method, path, payload_builder in profile.get("requests") or []:
        if name in seen_names:
            continue
        requests.append(_build_snapshot_request(name, method, path, payload_builder(project_id, serial_no)))
        seen_names.add(name)
    return requests


def build_initiation_snapshot_requests(project_id: str, *, category: str = "", serial_no: str = "") -> list[dict[str, Any]]:
    return [
        {
            "name": "project_base_info",
            "method": "POST",
            "path": "/projectBaseInfo/info",
            "payload": {"projectId": project_id},
        },
        {"name": "project_uploading", "method": "GET", "path": f"/projectUploading/list/{project_id}", "payload": None},
        *build_category_review_requests(project_id, category=category, serial_no=serial_no),
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


def build_acceptance_snapshot_requests(
    *,
    budget_project_id: str,
    establishment_project_id: str,
    category: str = "",
    serial_no: str = "",
) -> list[dict[str, Any]]:
    return [
        *build_initiation_snapshot_requests(establishment_project_id, category=category, serial_no=serial_no),
        {
            "name": "acceptance_info_list",
            "method": "GET",
            "path": f"/acceptDetail/acceptInfoList?projectId={urllib.parse.quote(str(budget_project_id or '').strip())}",
            "payload": None,
        },
    ]


def build_project_snapshot_requests(project_id: str, scene: str = "initiation", *, category: str = "", serial_no: str = "") -> list[dict[str, Any]]:
    if normalize_scene(scene) == "acceptance":
        return build_acceptance_snapshot_requests(
            budget_project_id=project_id,
            establishment_project_id=project_id,
            category=category,
            serial_no=serial_no,
        )
    return build_initiation_snapshot_requests(project_id, category=category, serial_no=serial_no)


def extract_establishment_project_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ["projectEstablishmentId", "establishProjectId", "projectEstablishId"]:
            text = str(value.get(key) or "").strip()
            if text:
                return text
        for nested in value.values():
            resolved = extract_establishment_project_id(nested)
            if resolved:
                return resolved
        return ""
    if isinstance(value, list):
        for item in value:
            resolved = extract_establishment_project_id(item)
            if resolved:
                return resolved
    return ""


def _collect_accept_ids_from_value(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        direct_accept_id = str(
            first_non_empty(
                value.get("acceptId"),
                value.get("acceptid"),
                value.get("accept_id"),
                value.get("id")
                if (
                    "id" in value
                    and (
                        "establishProjectId" in value
                        or "acceptTotalFee" in value
                        or "processInstanceType" in value
                        or "isFinalAccept" in value
                    )
                )
                else "",
            )
            or ""
        ).strip()
        if direct_accept_id and len(direct_accept_id) >= 6:
            output.add(direct_accept_id)
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if "accept" in normalized_key and "id" in normalized_key:
                text = str(nested or "").strip()
                if text and len(text) >= 6:
                    output.add(text)
            _collect_accept_ids_from_value(nested, output)
        return
    if isinstance(value, list):
        for item in value:
            _collect_accept_ids_from_value(item, output)


def collect_accept_ids(endpoint_results: dict[str, dict[str, Any]]) -> list[str]:
    values: set[str] = set()
    for endpoint in endpoint_results.values():
        _collect_accept_ids_from_value((endpoint or {}).get("data"), values)
    return sorted(values)


def build_acceptance_detail_requests(project_id: str, accept_id: str) -> list[dict[str, Any]]:
    return [
        {
            "name": f"acceptance_task_info__{accept_id}",
            "method": "POST",
            "path": "/projectAcceptNew/getProjectTaskInfoList",
            "payload": {"projectId": project_id, "acceptId": accept_id},
        },
        {
            "name": f"acceptance_contract_info__{accept_id}",
            "method": "GET",
            "path": (
                f"/contract/getNewAcceptContract?number=99999&page=1"
                f"&projectId={urllib.parse.quote(str(project_id or '').strip())}"
                f"&status=2&acceptid={urllib.parse.quote(str(accept_id or '').strip())}"
            ),
            "payload": None,
        },
        {
            "name": f"acceptance_stage_tasks__{accept_id}",
            "method": "GET",
            "path": f"/acceptDetail/taskList/{accept_id}",
            "payload": None,
        },
        {
            "name": f"acceptance_stage_contracts__{accept_id}",
            "method": "GET",
            "path": f"/acceptDetail/contractList/{accept_id}",
            "payload": None,
        },
        {
            "name": f"acceptance_count_data__{accept_id}",
            "method": "GET",
            "path": f"/acceptDetail/countData/{accept_id}",
            "payload": None,
        },
        {
            "name": f"acceptance_architecture_elements__{accept_id}",
            "method": "GET",
            "path": f"/projectAccept/queryAcceptElementList?projectId={project_id}&acceptId={accept_id}&elementType=9",
            "payload": None,
        },
    ]


def aggregate_acceptance_detail_results(
    detail_results: dict[str, dict[str, Any]],
    endpoint_results: dict[str, dict[str, Any]],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {
        "acceptance_task_info": [],
        "acceptance_contract_info": [],
        "acceptance_stage_tasks": [],
        "acceptance_stage_contracts": [],
        "acceptance_count_data": [],
        "acceptance_architecture_elements": [],
    }
    for name, result in detail_results.items():
        endpoint_type, _, accept_id = str(name).partition("__")
        if endpoint_type not in grouped:
            continue
        grouped[endpoint_type].append(
            {
                "acceptId": accept_id,
                "ok": bool(result.get("ok")),
                "code": result.get("code"),
                "message": result.get("message"),
                "data": result.get("data"),
            }
        )

    for endpoint_type, items in grouped.items():
        if not items:
            continue
        endpoint_results[endpoint_type] = {
            "ok": any(bool(item.get("ok")) for item in items),
            "code": 0 if any(bool(item.get("ok")) for item in items) else -1,
            "message": "aggregated",
            "data": items,
        }
