from __future__ import annotations

from typing import Any


def _normalize_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        for key in ["dataList", "list", "rows", "records", "items", "reviewResult", "dimensionList"]:
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def pick_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def normalize_review_conclusion(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in {"1", "通过", "pass", "PASS"}:
        return "通过"
    if normalized in {"0", "不涉及", "not involved", "NOT INVOLVED"}:
        return "不涉及"
    if normalized in {"不通过", "fail", "FAIL"}:
        return "不通过"
    return normalized


def sum_unique_ints(rows: list[dict[str, Any]], key: str, identity_key: str) -> int:
    values: dict[str, int] = {}
    for row in rows:
        identity = str(row.get(identity_key) or row.get("id") or "").strip()
        if not identity:
            identity = f"row-{len(values)}"
        try:
            values[identity] = max(values.get(identity, 0), int(row.get(key) or 0))
        except Exception:
            values[identity] = values.get(identity, 0)
    return sum(values.values())


def iter_tree_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    stack = list(nodes)
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        items.append(current)
        children = current.get("children")
        if isinstance(children, list):
            stack.extend(children)
    return items


def extract_product_context(snapshot: dict[str, Any]) -> dict[str, str]:
    dev_scope = ((snapshot.get("endpoints") or {}).get("project_scope_dev") or {}).get("data") or {}
    flow_rows = _normalize_list(dev_scope.get("projectRangeFlowEntities"))
    for row in flow_rows:
        if not isinstance(row, dict):
            continue
        product_id = str(row.get("productId") or "").strip()
        if product_id:
            return {"product_id": product_id, "product_name": str(row.get("productName") or "").strip()}
    return {"product_id": "", "product_name": ""}


def build_business_review_summary(snapshot: dict[str, Any]) -> dict[str, int]:
    dev_scope = ((snapshot.get("endpoints") or {}).get("project_scope_dev") or {}).get("data") or {}
    flow_rows = [item for item in _normalize_list(dev_scope.get("projectRangeFlowEntities")) if isinstance(item, dict)]
    unique_product_ids = {str(item.get("productId") or "").strip() for item in flow_rows if str(item.get("productId") or "").strip()}
    unique_process_ids = {
        str(item.get("processVersionId") or item.get("processId") or item.get("id") or "").strip()
        for item in flow_rows
        if str(item.get("processVersionId") or item.get("processId") or item.get("id") or "").strip()
    }
    tree_nodes = iter_tree_nodes(_normalize_list(dev_scope.get("projectRangeEaMapTreeEntities")))
    business_object_count = sum_unique_ints(flow_rows, "busObjNum", "processVersionId")
    if not business_object_count:
        business_object_count = len(
            [
                node
                for node in tree_nodes
                if "对象" in str(node.get("type") or "") or "对象" in str(node.get("typeName") or "") or "对象" in str(node.get("name") or "")
            ]
        )
    return {
        "product_count": len(unique_product_ids),
        "business_process_count": len(unique_process_ids),
        "business_unit_count": sum_unique_ints(flow_rows, "busNum", "processVersionId"),
        "business_object_count": business_object_count,
    }


def normalize_review_items(items: Any) -> list[dict[str, Any]]:
    rows = _normalize_list(items)
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            normalized.append(
                {
                    "id": f"review-{index}",
                    "index": index,
                    "dimension": "",
                    "checkpoint": str(row),
                    "value_model": "",
                    "reviewer": "",
                    "conclusion": "",
                    "description": "",
                }
            )
            continue
        normalized.append(
            {
                "id": str(row.get("id") or f"review-{index}"),
                "index": index,
                "dimension": pick_text(row, "dimension", "dimensionName", "typeName", "type"),
                "checkpoint": pick_text(row, "checkpoint", "checkPoint", "checkpointName", "name", "title"),
                "value_model": pick_text(
                    row,
                    "valuePropositionModel",
                    "reviewModel",
                    "reviewStandard",
                    "reviewContent",
                    "content",
                    "description",
                ),
                "reviewer": pick_text(
                    row,
                    "reviewer",
                    "initialReviewer",
                    "preliminaryInterrogator",
                    "creator",
                    "createUser",
                    "auditUser",
                ),
                "conclusion": normalize_review_conclusion(
                    pick_text(
                        row,
                        "reviewConclusion",
                        "preliminaryConclusion",
                        "conclusion",
                        "result",
                        "statusName",
                        "status",
                    )
                ),
                "description": pick_text(row, "reviewDescription", "remark", "opinion", "description"),
            }
        )
    return normalized


def normalize_technology_review_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ["dimensionList", "checkList", "checklist", "reviewResultList", "list", "items"]:
            nested = data.get(key)
            if nested not in (None, "", []):
                items = normalize_review_items(nested)
                if items:
                    return items
        review_result = data.get("reviewResult")
        if isinstance(review_result, (list, dict)) and review_result not in ({}, []):
            items = normalize_review_items(review_result)
            if items:
                return items
    return normalize_review_items(data)


def is_information_architecture_item(item: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(item.get("dimension") or ""),
            str(item.get("checkpoint") or ""),
            str(item.get("value_model") or ""),
        ]
    )
    return "信息架构" in haystack or "概念模型" in haystack or "业务对象" in haystack
