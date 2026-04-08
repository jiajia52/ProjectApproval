from __future__ import annotations

from concurrent import futures
from typing import Any

from app.approvals.clients.iwork_client import IworkProjectClient
from app.approvals.review.architecture_review_utils import (
    build_review_error_group as _build_review_error_group,
    normalize_list,
    snapshot_endpoint_payload as _snapshot_endpoint_payload,
)
from app.approvals.review.review_helpers import (
    build_business_review_summary as _build_business_review_summary,
    extract_product_context as _extract_product_context,
    is_information_architecture_item as _is_information_architecture_item,
    normalize_review_conclusion as _normalize_review_conclusion,
    normalize_review_items as _normalize_review_items,
    normalize_technology_review_items as _normalize_technology_review_items,
    pick_text as _pick_text,
)


def _fetch_data_review(client: IworkProjectClient, project_id: str) -> dict[str, Any]:
    result = client.request_json(
        "GET",
        f"/initiationTask/result?projectId={project_id}",
        strict=False,
        api_name="architecture_review_data",
        project_id=project_id,
    )
    data = result.get("data")
    items = _normalize_review_items(data)
    return {
        "key": "data",
        "title": "数据架构评审状态",
        "link_label": "前往信息架构中心查看",
        "ok": result.get("code") == 0,
        "message": str(result.get("message") or ""),
        "summary": {
            "flow_dimension_count": len({item.get("dimension") for item in items if item.get("dimension")}),
            "check_point_count": len(items),
        },
        "items": items,
    }


def _fetch_technology_review_fallback(client: IworkProjectClient, project_id: str) -> dict[str, Any]:
    result = client.request_json(
        "POST",
        "/projectMicosInfo/getList",
        payload={"projectId": project_id, "dataType": 1},
        strict=False,
        api_name="architecture_review_technology_fallback",
        project_id=project_id,
    )
    items: list[dict[str, Any]] = []
    for index, row in enumerate(normalize_list(result.get("data")), start=1):
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "id": str(row.get("id") or f"tech-fallback-{index}"),
                "index": index,
                "dimension": "技术架构",
                "checkpoint": _pick_text(row, "subName", "systemName", "name"),
                "value_model": f"系统编码: {_pick_text(row, 'systemCode', 'subCode')}；负责人: {_pick_text(row, 'subLeader', 'owner', 'leader')}",
                "reviewer": "",
                "conclusion": "通过",
                "description": _pick_text(row, "subLevelStandard", "subType", "systemName"),
            }
        )
    return {
        "key": "technology",
        "title": "技术架构评审状态",
        "link_label": "前往云原生查看",
        "ok": result.get("code") == 0 and len(items) > 0,
        "message": "技术架构评审接口未返回明细，已回退使用系统范围(dataType=1)内容作为技术架构材料。"
        if items
        else str(result.get("message") or ""),
        "summary": {
            "app_count": 0,
            "service_count": len(items),
            "type": "fallback",
        },
        "items": items,
    }


def _fetch_technology_review(client: IworkProjectClient, project_id: str) -> dict[str, Any]:
    type_values = [1, 2, 3, 4, 5, 6]
    candidates: list[dict[str, Any]] = []

    with futures.ThreadPoolExecutor(max_workers=min(6, len(type_values))) as executor:
        future_map = {
            executor.submit(
                client.request_json,
                "POST",
                "/third/techCheckList",
                payload={"projectId": project_id, "type": type_value},
                strict=False,
                api_name=f"architecture_review_technology_type_{type_value}",
                project_id=project_id,
            ): type_value
            for type_value in type_values
        }
        for future in futures.as_completed(future_map):
            type_value = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"code": -1, "message": str(exc), "data": {}}
            data = result.get("data") or {}
            items = _normalize_technology_review_items(data)
            candidates.append(
                {
                    "type": type_value,
                    "result": result,
                    "items": items,
                    "data": data,
                }
            )

    if not candidates:
        fallback = _fetch_technology_review_fallback(client, project_id)
        if fallback.get("ok"):
            return fallback
        raise RuntimeError("Technology architecture review returned no candidates.")

    candidates.sort(key=lambda item: int(item.get("type") or 0))
    chosen = next(
        (
            item
            for item in candidates
            if item["result"].get("code") == 200
            and (item["items"] or int((item["data"] or {}).get("appCount") or 0) or int((item["data"] or {}).get("serviceCount") or 0))
        ),
        candidates[0],
    )
    chosen_data = chosen.get("data") or {}
    result = chosen["result"]
    if not chosen["items"]:
        fallback = _fetch_technology_review_fallback(client, project_id)
        if fallback.get("ok"):
            return fallback
    return {
        "key": "technology",
        "title": "技术架构评审状态",
        "link_label": "前往云原生查看",
        "ok": result.get("code") == 200,
        "message": str(result.get("message") or ""),
        "summary": {
            "app_count": int(chosen_data.get("appCount") or 0),
            "service_count": int(chosen_data.get("serviceCount") or 0),
            "type": chosen["type"],
        },
        "items": chosen["items"],
    }


def _fetch_security_review(client: IworkProjectClient, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    endpoints = snapshot.get("endpoints") or {}
    base_info = (endpoints.get("project_base_info") or {}).get("data") or {}
    dev_scope = (endpoints.get("project_scope_dev") or {}).get("data") or {}
    related_systems = [item for item in normalize_list(dev_scope.get("projectRelatedSystemEntities")) if isinstance(item, dict)]
    system_code = str((related_systems[0].get("code") if related_systems else "") or "").strip()
    payload = {
        "projectId": project_id,
        "projectCode": str(base_info.get("serialNo") or "").strip(),
        "systemCode": system_code,
        "type": 1,
    }
    result = client.request_json(
        "POST",
        "/third/securityCheckList",
        payload=payload,
        strict=False,
        api_name="architecture_review_security",
        project_id=project_id,
    )
    data = result.get("data") or {}
    items = _normalize_review_items(data)
    return {
        "key": "security",
        "title": "安全架构评审状态",
        "link_label": "前往应用开发安全平台查看",
        "ok": result.get("code") == 200,
        "message": str(result.get("message") or ""),
        "summary": {
            "app_count": int(data.get("appCount") or 0),
            "service_count": int(data.get("serviceCount") or 0),
            "safety_level": str(data.get("safetyLevel") or ""),
        },
        "items": items,
    }


def build_architecture_review_groups_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    product_context = _extract_product_context(snapshot)

    business_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_business")
    business_items = _normalize_review_items(business_payload.get("data"))
    info_architecture_items = [item for item in business_items if _is_information_architecture_item(item)]
    business_items = [item for item in business_items if not _is_information_architecture_item(item)]
    business_group = {
        "key": "business",
        "title": "业务架构评审状态",
        "link_label": "前往EAMAP查看",
        "ok": bool(business_items),
        "message": str(business_payload.get("message") or ""),
        "summary": _build_business_review_summary(snapshot),
        "items": business_items,
        "context": product_context,
    }

    data_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_data")
    data_items = _normalize_review_items(data_payload.get("data"))
    merged_data_items = info_architecture_items + data_items
    data_message = str(data_payload.get("message") or "")
    if info_architecture_items:
        data_message = f"{data_message} Merged information-architecture items from business review.".strip()
    data_group = {
        "key": "data",
        "title": "数据架构评审状态",
        "link_label": "前往信息架构中心查看",
        "ok": bool(merged_data_items),
        "message": data_message,
        "summary": {
            "flow_dimension_count": len({item.get("dimension") for item in merged_data_items if item.get("dimension")}),
            "check_point_count": len(merged_data_items),
        },
        "items": merged_data_items,
    }

    technology_group = _build_review_error_group("technology", "技术架构评审状态", "前往云原生查看", "")
    fallback_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_technology_fallback")
    fallback_items = _normalize_review_items(fallback_payload.get("data"))
    technology_candidates: list[dict[str, Any]] = []
    for type_value in [1, 2, 3, 4, 5, 6]:
        payload = _snapshot_endpoint_payload(snapshot, f"architecture_review_technology_type_{type_value}")
        if not payload:
            continue
        data = payload.get("data") or {}
        items = _normalize_technology_review_items(data)
        technology_candidates.append(
            {
                "type": type_value,
                "payload": payload,
                "data": data,
                "items": items,
            }
        )
    chosen_technology = next(
        (
            candidate
            for candidate in technology_candidates
            if candidate["payload"].get("code") == 200
            and (
                candidate["items"]
                or int((candidate["data"] or {}).get("appCount") or 0)
                or int((candidate["data"] or {}).get("serviceCount") or 0)
            )
        ),
        None,
    )
    if chosen_technology and chosen_technology["items"]:
        chosen_data = chosen_technology.get("data") or {}
        payload = chosen_technology.get("payload") or {}
        technology_group = {
            "key": "technology",
            "title": "技术架构评审状态",
            "link_label": "前往云原生查看",
            "ok": True,
            "message": str(payload.get("message") or ""),
            "summary": {
                "app_count": int(chosen_data.get("appCount") or 0),
                "service_count": int(chosen_data.get("serviceCount") or 0),
                "type": chosen_technology.get("type"),
            },
            "items": chosen_technology["items"],
        }
    elif fallback_items:
        technology_group = {
            "key": "technology",
            "title": "技术架构评审状态",
            "link_label": "前往云原生查看",
            "ok": True,
            "message": str(
                fallback_payload.get("message")
                or "技术架构评审接口未返回明细，已回退使用系统范围(dataType=1)内容作为技术架构材料。"
            ),
            "summary": {
                "app_count": 0,
                "service_count": len(fallback_items),
                "type": "fallback",
            },
            "items": fallback_items,
        }

    security_payload = _snapshot_endpoint_payload(snapshot, "architecture_review_security")
    security_data = security_payload.get("data") or {}
    security_items = _normalize_review_items(security_data)
    security_group = {
        "key": "security",
        "title": "安全架构评审状态",
        "link_label": "前往应用开发安全平台查看",
        "ok": bool(security_items),
        "message": str(security_payload.get("message") or ""),
        "summary": {
            "app_count": int(security_data.get("appCount") or 0),
            "service_count": int(security_data.get("serviceCount") or 0),
            "safety_level": str(security_data.get("safetyLevel") or ""),
        },
        "items": security_items,
    }

    return [business_group, data_group, technology_group, security_group]


def _acceptance_review_group_key(item: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            str(item.get("dimension") or ""),
            str(item.get("checkpoint") or ""),
            str(item.get("value_model") or ""),
            str(item.get("description") or ""),
        ]
    ).lower()
    if any(keyword in haystack for keyword in ["security", "safe", "安全"]):
        return "security"
    if any(keyword in haystack for keyword in ["data", "信息", "数据", "模型", "对象"]):
        return "data"
    if any(keyword in haystack for keyword in ["business", "eamap", "流程", "业务", "okr"]):
        return "business"
    if any(keyword in haystack for keyword in ["technology", "tech", "技术", "架构", "应用", "微服务", "cloud", "云"]):
        return "technology"
    return "technology"


def _build_acceptance_review_group(
    key: str,
    title: str,
    link_label: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, Any]
    if key == "business":
        summary = {
            "business_process_count": len(items),
            "business_object_count": len(
                {str(item.get("checkpoint") or "").strip() for item in items if str(item.get("checkpoint") or "").strip()}
            ),
        }
    elif key == "data":
        summary = {
            "flow_dimension_count": len({str(item.get("dimension") or "").strip() for item in items if str(item.get("dimension") or "").strip()}),
            "check_point_count": len(items),
        }
    else:
        summary = {"service_count": len(items)}
    return {
        "key": key,
        "title": title,
        "link_label": link_label,
        "ok": len(items) > 0,
        "message": "" if items else "No acceptance review items were returned for this dimension.",
        "summary": summary,
        "items": items,
    }


def collect_acceptance_architecture_review_groups(document: dict[str, Any]) -> list[dict[str, Any]]:
    acceptance = document.get("acceptance") or {}
    raw_items = normalize_list(acceptance.get("architecture_elements"))
    normalized_items: list[dict[str, Any]] = []
    for index, row in enumerate(raw_items, start=1):
        if not isinstance(row, dict):
            continue
        normalized_items.append(
            {
                "id": str(row.get("id") or f"acceptance-review-{index}"),
                "index": int(row.get("index") or index),
                "dimension": _pick_text(row, "dimension", "dimensionName", "typeName", "type"),
                "checkpoint": _pick_text(row, "checkpoint", "checkPoint", "checkpointName", "name", "title"),
                "value_model": _pick_text(
                    row,
                    "value_model",
                    "valueModel",
                    "reviewModel",
                    "reviewStandard",
                    "reviewContent",
                    "content",
                    "description",
                ),
                "reviewer": _pick_text(
                    row,
                    "reviewer",
                    "reviewerName",
                    "initialReviewer",
                    "creator",
                    "createUser",
                    "auditUser",
                ),
                "conclusion": _normalize_review_conclusion(
                    _pick_text(
                        row,
                        "conclusion",
                        "reviewConclusion",
                        "reviewResultName",
                        "reviewResult",
                        "preliminaryConclusion",
                        "result",
                        "statusName",
                        "status",
                    )
                ),
                "description": _pick_text(row, "description", "reviewDescription", "remark", "opinion", "detail"),
            }
        )

    grouped_items: dict[str, list[dict[str, Any]]] = {
        "business": [],
        "data": [],
        "technology": [],
        "security": [],
    }
    for item in normalized_items:
        grouped_items[_acceptance_review_group_key(item)].append(item)

    return [
        _build_acceptance_review_group("business", "Business Architecture Review", "Open Acceptance Review", grouped_items["business"]),
        _build_acceptance_review_group("data", "Data Architecture Review", "Open Acceptance Review", grouped_items["data"]),
        _build_acceptance_review_group(
            "technology",
            "Technology Architecture Review",
            "Open Acceptance Review",
            grouped_items["technology"],
        ),
        _build_acceptance_review_group("security", "Security Architecture Review", "Open Acceptance Review", grouped_items["security"]),
    ]


def collect_architecture_review_groups(
    *,
    client: IworkProjectClient,
    project_id: str,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    product_context = _extract_product_context(snapshot)
    business_items: list[dict[str, Any]] = []
    business_ok = False
    business_message = ""
    if product_context["product_id"]:
        try:
            business_result = client.request_json(
                "GET",
                f"/projectBaseInfo/getProductCheckStatus/{product_context['product_id']}",
                strict=False,
                api_name="architecture_review_business",
                project_id=project_id,
            )
            business_items = _normalize_review_items(business_result.get("data"))
            business_ok = business_result.get("code") == 0
            business_message = str(business_result.get("message") or "")
        except Exception as exc:
            business_message = str(exc)
    else:
        business_message = "未在项目范围-开发接口中找到产品ID，无法调用业务架构评审接口。"

    info_architecture_items = [item for item in business_items if _is_information_architecture_item(item)]
    business_items = [item for item in business_items if not _is_information_architecture_item(item)]

    groups = [
        {
            "key": "business",
            "title": "业务架构评审状态",
            "link_label": "前往EAMAP查看",
            "ok": business_ok and len(business_items) > 0,
            "message": business_message,
            "summary": _build_business_review_summary(snapshot),
            "items": business_items,
            "context": product_context,
        }
    ]

    async_groups: dict[str, dict[str, Any]] = {}
    async_errors: dict[str, str] = {}
    with futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(_fetch_data_review, client, project_id): "data",
            executor.submit(_fetch_technology_review, client, project_id): "technology",
            executor.submit(_fetch_security_review, client, project_id, snapshot): "security",
        }
        for future in futures.as_completed(future_map):
            group_key = future_map[future]
            try:
                async_groups[group_key] = future.result()
            except Exception as exc:
                async_errors[group_key] = str(exc)

    data_group = async_groups.get("data")
    if data_group is None:
        data_group = _build_review_error_group(
            "data",
            "Data Architecture Review",
            "Open Data Architecture Center",
            async_errors.get("data", "Unknown error"),
        )
    merged_items = info_architecture_items + list(data_group.get("items") or [])
    data_group["items"] = merged_items
    data_group["ok"] = bool(data_group.get("ok") or merged_items)
    data_group["summary"] = {
        "flow_dimension_count": len({item.get("dimension") for item in merged_items if item.get("dimension")}),
        "check_point_count": len(merged_items),
    }
    if info_architecture_items:
        base_message = str(data_group.get("message") or "").strip()
        data_group["message"] = f"{base_message} Merged information-architecture items from business review.".strip()
    groups.append(data_group)

    technology_group = async_groups.get("technology")
    if technology_group is None:
        technology_group = _build_review_error_group(
            "technology",
            "Technology Architecture Review",
            "Open Cloud Native Portal",
            async_errors.get("technology", "Unknown error"),
        )
    groups.append(technology_group)

    security_group = async_groups.get("security")
    if security_group is None:
        security_group = _build_review_error_group(
            "security",
            "Security Architecture Review",
            "Open Security Portal",
            async_errors.get("security", "Unknown error"),
        )
    groups.append(security_group)

    return groups
