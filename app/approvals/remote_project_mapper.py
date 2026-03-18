"""Map remote iwork project snapshots into the approval document schema."""

from __future__ import annotations

import re
from typing import Any


SECTION_KEYWORDS = {
    "background": ["背景", "鑳屾櫙"],
    "target": ["目标", "鐩爣"],
    "solution": ["方案", "鏂规"],
    "panorama": ["全景", "鍏ㄦ櫙"],
    "annual_model": ["管理模型", "年度", "绠＄悊妯″瀷", "骞村害"],
}

UPLOAD_SECTION_BY_CODE = {
    "1": "background",
    "2": "target",
    "3": "solution",
    "4": "panorama",
    "5": "annual_model",
}

MILESTONE_KEYWORDS = {
    "approval_plan": ["立项", "绔嬮】"],
    "contract_plan": ["合同", "鍚堝悓"],
    "target_plan": ["目标", "鐩爣"],
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(part for part in (normalize_text(item) for item in value) if part)
    if isinstance(value, dict):
        return "\n".join(f"{key}:{part}" for key, part in ((k, normalize_text(v)) for k, v in value.items()) if part)
    return str(value).strip()


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def normalize_procurement_method(value: Any) -> str:
    normalized = str(value or "").strip()
    mapping = {
        "1": "直接采购",
        "2": "招标采购",
        "3": "询比采购",
        "4": "竞争性谈判",
        "5": "单一来源",
        "6": "开发资源池",
    }
    return mapping.get(normalized, normalized)


def normalize_organization_party_type(item: dict[str, Any]) -> str:
    flag = str(item.get("flag") or "").strip()
    if flag == "1":
        return "third"
    if flag == "0":
        return "own"
    people_belong = normalize_text(item.get("peopleBelong"))
    if "三方" in people_belong or "外部" in people_belong:
        return "third"
    type_value = str(item.get("type") or "").strip()
    if type_value in {"1", "2"}:
        return "third"
    return "own"


def deep_collect_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        records.append(value)
        for nested in value.values():
            records.extend(deep_collect_records(nested))
    elif isinstance(value, list):
        for item in value:
            records.extend(deep_collect_records(item))
    return records


def guess_section_name(record: dict[str, Any]) -> str | None:
    haystack = normalize_text(record).lower()
    for section_name, keywords in SECTION_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            return section_name
    return None


def map_upload_section(value: Any) -> str | None:
    if value is None:
        return None
    return UPLOAD_SECTION_BY_CODE.get(str(value).strip())


def extract_title_order(title: str) -> int | None:
    match = re.match(r"^\s*(\d+)\s*[、.．:：\-)）]?", title or "")
    if not match:
        return None
    return int(match.group(1))


def collect_image_candidates(record: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for key in ["images", "imageList", "fileList", "attachments", "files"]:
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text:
                    images.append(text)
    for key in ["imageUrl", "image", "fileUrl", "url", "path"]:
        value = str(record.get(key) or "").strip()
        if value:
            images.append(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in images:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def build_empty_upload_section() -> dict[str, Any]:
    return {"title": "", "content": "", "images": [], "items": []}


def sort_upload_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item.get("sort_order") if item.get("sort_order") is not None else item.get("source_index", 10**9),
            item.get("source_index", 10**9),
        ),
    )


def extract_upload_sections(upload_data: Any) -> dict[str, dict[str, Any]]:
    sections = {
        "background": build_empty_upload_section(),
        "target": build_empty_upload_section(),
        "solution": build_empty_upload_section(),
        "panorama": build_empty_upload_section(),
        "annual_model": build_empty_upload_section(),
    }

    def apply_record(record: dict[str, Any], source_index: int, forced_section: str | None = None) -> None:
        section_name = forced_section or map_upload_section(record.get("type")) or guess_section_name(record)
        if not section_name:
            return
        title = (
            record.get("title")
            or record.get("uploadTitle")
            or record.get("fileName")
            or record.get("name")
            or record.get("moduleName")
            or ""
        )
        content = (
            record.get("content")
            or record.get("uploadContent")
            or record.get("remark")
            or record.get("description")
            or ""
        )
        image_candidates = collect_image_candidates(record)
        if not str(title or "").strip() and not str(content or "").strip() and not image_candidates:
            return
        section = sections[section_name]
        section["items"].append(
            {
                "title": str(title or ""),
                "content": str(content or ""),
                "images": image_candidates,
                "sort_order": extract_title_order(str(title or "")),
                "source_index": source_index,
            }
        )
        if title and not section["title"]:
            section["title"] = str(title)
        if content and len(str(content)) > len(section["content"]):
            section["content"] = str(content)
        if image_candidates:
            existing = {str(item) for item in section["images"]}
            section["images"].extend(item for item in image_candidates if item not in existing)

    source_index = 0
    if isinstance(upload_data, dict):
        consumed_ids: set[int] = set()
        for key, value in upload_data.items():
            section_name = map_upload_section(key)
            if not section_name or not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict):
                    apply_record(item, source_index, section_name)
                    consumed_ids.add(id(item))
                    source_index += 1
        for record in deep_collect_records(upload_data):
            if id(record) in consumed_ids:
                continue
            apply_record(record, source_index)
            source_index += 1
    else:
        for record in deep_collect_records(upload_data):
            apply_record(record, source_index)
            source_index += 1

    for section in sections.values():
        ordered_items = sort_upload_items(section["items"])
        section["items"] = [
            {
                "title": item["title"],
                "content": item["content"],
                "images": item["images"],
                "order": item["sort_order"],
            }
            for item in ordered_items
        ]
        if section["items"]:
            first_item = section["items"][0]
            if not section["title"]:
                section["title"] = first_item.get("title", "")
            if not section["content"]:
                section["content"] = first_item.get("content", "")
            if not section["images"]:
                section["images"] = list(first_item.get("images", []))
    return sections


def list_from_data(data: Any) -> list[Any]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if not data:
            return []
        for key in ["dataList", "list", "rows", "records", "items", "partInfos", "projectRangeFlowEntities", "projectRange"]:
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]
    return [data]


def pick_preferred_payload(*values: Any) -> Any:
    for value in values:
        if list_from_data(value):
            return value
    for value in values:
        if isinstance(value, dict) and value:
            return value
        if isinstance(value, list) and value:
            return value
    return {}


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def extract_change_history_rows(change_data: Any) -> tuple[list[dict[str, Any]], list[str], float]:
    rows: list[dict[str, Any]] = []
    previous_projects: list[str] = []
    history_total_cost = 0.0

    for item in list_from_data(change_data):
        if not isinstance(item, dict):
            continue

        project_year = first_non_empty(
            item.get("projectYear"),
            item.get("year"),
            item.get("budgetYear"),
            item.get("applyYear"),
            item.get("proBudgetYear"),
        )
        project_name = normalize_text(
            first_non_empty(
                item.get("projectName"),
                item.get("preProjectName"),
                item.get("beforeProjectName"),
                item.get("relationProjectName"),
                item.get("name"),
                item.get("serialNo"),
            )
        )
        project_content = normalize_text(
            first_non_empty(
                item.get("projectContent"),
                item.get("content"),
                item.get("projectDesc"),
                item.get("description"),
                item.get("analysis"),
            )
        )
        project_amount = first_non_empty(
            item.get("projectAmount"),
            item.get("proBudget"),
            item.get("budget"),
            item.get("amount"),
            item.get("expectFee"),
            item.get("historyAmount"),
            item.get("totalAmount"),
        )
        related_cost = first_non_empty(
            item.get("relatedCost"),
            item.get("involveFee"),
            item.get("cost"),
            item.get("changeCost"),
            item.get("changeAmount"),
            item.get("threeValue"),
        )

        if not any(normalize_text(value) for value in [project_year, project_name, project_content, project_amount, related_cost]):
            continue

        if project_name:
            previous_projects.append(project_name)

        amount_number = to_float(project_amount)
        related_cost_number = to_float(related_cost)
        if amount_number is not None:
            history_total_cost += amount_number
        elif related_cost_number is not None:
            history_total_cost += related_cost_number

        rows.append(
            {
                "index": len(rows) + 1,
                "project_year": normalize_text(project_year),
                "project_name": project_name,
                "project_content": project_content,
                "project_amount": project_amount,
                "related_cost": related_cost,
            }
        )

    deduped_projects: list[str] = []
    seen: set[str] = set()
    for project in previous_projects:
        if project in seen:
            continue
        seen.add(project)
        deduped_projects.append(project)
    return rows, deduped_projects, history_total_cost


def build_time_range(raw_goal: Any) -> dict[str, Any]:
    if isinstance(raw_goal, dict):
        start = raw_goal.get("targetStartTime") or raw_goal.get("startTime") or raw_goal.get("startDate")
        end = raw_goal.get("targetEndTime") or raw_goal.get("endTime") or raw_goal.get("endDate")
        return {"start": start or "", "end": end or ""}
    return {"start": "", "end": ""}


def normalize_goal_payload(raw_goal: Any) -> dict[str, Any]:
    goal_items = [item for item in list_from_data(raw_goal) if isinstance(item, dict)]
    if not goal_items:
        return {}

    primary = goal_items[0]
    related_products: list[Any] = []
    key_results: list[Any] = []
    goal_names: list[str] = []
    squad_names: list[str] = []
    starts: list[str] = []
    ends: list[str] = []
    related_product_names: list[str] = []

    for item in goal_items:
        goal_name = normalize_text(item.get("goalName") or item.get("objective"))
        if goal_name:
            goal_names.append(goal_name)
        squad_name = normalize_text(item.get("teamOkr") or item.get("troopOkr") or item.get("okrName"))
        if squad_name:
            squad_names.append(squad_name)
        start = item.get("targetStartTime") or item.get("startTime") or item.get("startDate")
        end = item.get("targetEndTime") or item.get("endTime") or item.get("endDate")
        if start:
            starts.append(str(start))
        if end:
            ends.append(str(end))
        current_related_products = list_from_data(
            item.get("relationProductList")
            or item.get("productList")
            or item.get("subProductDtoList")
            or []
        )
        related_products.extend(current_related_products)
        for product in current_related_products:
            if isinstance(product, dict):
                product_name = normalize_text(
                    product.get("productLineName")
                    or product.get("productChainName")
                    or product.get("productName")
                    or product.get("name")
                )
                if product_name:
                    related_product_names.append(product_name)
        key_results.extend(list_from_data(item.get("krList") or item.get("keyResults") or item.get("keyResultDtoList") or []))

    inferred_product_chain = "\n".join(dict.fromkeys(related_product_names))

    return {
        "productLineName": first_non_empty(primary.get("productLineName"), primary.get("productChainName"), inferred_product_chain),
        "productChainName": first_non_empty(primary.get("productChainName"), primary.get("productLineName"), inferred_product_chain),
        "goalName": "\n".join(dict.fromkeys(goal_names)),
        "objective": "\n".join(dict.fromkeys(goal_names)),
        "teamOkr": "\n".join(dict.fromkeys(squad_names)),
        "troopOkr": "\n".join(dict.fromkeys(squad_names)),
        "relationProductList": related_products,
        "productList": related_products,
        "krList": key_results,
        "keyResults": key_results,
        "targetStartTime": starts[0] if starts else "",
        "startTime": starts[0] if starts else "",
        "targetEndTime": ends[-1] if ends else "",
        "endTime": ends[-1] if ends else "",
    }


def map_milestone_bucket(title: str) -> str | None:
    for section_name, keywords in MILESTONE_KEYWORDS.items():
        if any(keyword in title for keyword in keywords):
            return section_name
    return None


def walk_tree_records(value: Any, parents: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    parents = parents or []
    records: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            records.extend(walk_tree_records(item, parents))
        return records
    if not isinstance(value, dict):
        return records

    current_parents = [*parents, value]
    children = value.get("children")
    if isinstance(children, list) and children:
        for child in children:
            records.extend(walk_tree_records(child, current_parents))
    else:
        records.append({"node": value, "parents": parents})
    return records


def build_system_scope_fallback(scope_data: Any) -> list[dict[str, Any]]:
    if not isinstance(scope_data, dict):
        return []

    related_systems = list_from_data(
        scope_data.get("projectRelatedSystemEntities")
        or scope_data.get("projectRelatedSystems")
        or scope_data.get("relatedSystemEntities")
        or []
    )
    if related_systems:
        rows: list[dict[str, Any]] = []
        for item in related_systems:
            if not isinstance(item, dict):
                continue
            code = normalize_text(item.get("code"))
            name = normalize_text(item.get("name"))
            if not code and not name:
                continue
            rows.append(
                {
                    "id": item.get("id") or code or name,
                    "code": code,
                    "name": name,
                    "groupName": "系统",
                    "rootName": "系统",
                    "categoryName": "系统",
                    "systemName": name,
                    "applicationSystemName": name,
                    "appName": name,
                    "type": "system",
                    "typeName": "系统",
                    "ownerName": first_non_empty(item.get("ownerName"), item.get("systemLeader"), item.get("creator")),
                    "systemLeader": first_non_empty(item.get("systemLeader"), item.get("ownerName"), item.get("creator")),
                    "qualityLevel": first_non_empty(item.get("qualityLevel"), item.get("qualityGrade"), item.get("levelName")),
                    "gradeBasis": first_non_empty(item.get("gradeBasis"), item.get("remark"), item.get("description")),
                }
            )
        if rows:
            return rows

    tree_sources = [
        scope_data.get("systemRelationSystemTrees"),
        scope_data.get("systemTreeList"),
        scope_data.get("systemTrees"),
        scope_data.get("applicationSystemTrees"),
    ]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for tree_source in tree_sources:
        for entry in walk_tree_records(tree_source):
            node = entry.get("node") or {}
            parents = entry.get("parents") or []
            node_type = str(node.get("type") or "").strip().lower()
            if node_type and node_type not in {"system", "app", "application", "microapp", "microservice", "service"}:
                continue
            code = normalize_text(node.get("code"))
            name = normalize_text(node.get("name"))
            if not code and not name:
                continue
            record_id = normalize_text(node.get("id") or code or name)
            if record_id in seen:
                continue
            seen.add(record_id)
            parent_names = [normalize_text(item.get("name")) for item in parents if isinstance(item, dict)]
            rows.append(
                {
                    "id": node.get("id") or record_id,
                    "code": code,
                    "name": name,
                    "groupName": parent_names[0] if parent_names else "系统",
                    "rootName": parent_names[0] if parent_names else "系统",
                    "categoryName": parent_names[-1] if parent_names else "系统",
                    "systemName": name,
                    "applicationSystemName": name,
                    "appName": name,
                    "type": node_type or "system",
                    "typeName": first_non_empty(node.get("typeName"), "系统"),
                    "ownerName": first_non_empty(node.get("ownerName"), node.get("systemLeader"), node.get("principal")),
                    "systemLeader": first_non_empty(node.get("systemLeader"), node.get("ownerName"), node.get("principal")),
                    "qualityLevel": first_non_empty(node.get("qualityLevel"), node.get("qualityGrade"), node.get("levelName")),
                    "gradeBasis": first_non_empty(node.get("gradeBasis"), node.get("remark"), node.get("description")),
                }
            )
    return rows


def parse_tam_group_key(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized == "2":
        return "result"
    if normalized == "3":
        return "management"
    return "capability"


def normalize_tam_metric(item: dict[str, Any]) -> dict[str, Any]:
    one_year = first_non_empty(item.get("oneValue"), item.get("oneYearValue"), item.get("targetOneYear"), item.get("target_2026"))
    two_year = first_non_empty(item.get("twoValue"), item.get("twoYearValue"), item.get("targetTwoYear"), item.get("target_2027"))
    three_year = first_non_empty(item.get("threeValue"), item.get("threeYearValue"), item.get("targetThreeYear"), item.get("target_2028"))
    return {
        "id": first_non_empty(item.get("projectValueId"), item.get("id")),
        "title": first_non_empty(item.get("title"), item.get("name")),
        "current_state": first_non_empty(item.get("currentStatus"), item.get("current_state"), item.get("currentState"), item.get("status")),
        "benefit_department": first_non_empty(item.get("benefit_department"), item.get("benefitDepartment"), item.get("department"), item.get("deptId")),
        "target_3y": {
            "2026": one_year,
            "2027": two_year,
            "2028": three_year,
        },
        "target_2026": one_year,
        "target_2027": two_year,
        "target_2028": three_year,
        "calculation_basis": first_non_empty(item.get("content"), item.get("calculation_basis"), item.get("calculationBasis")),
    }


def extract_tam_models(tam_data: Any) -> dict[str, list[dict[str, Any]]]:
    groups = {"capability": [], "result": [], "management": []}
    if not isinstance(tam_data, dict):
        return groups

    direct_group_map = {
        "capabilityList": "capability",
        "abilityList": "capability",
        "resultList": "result",
        "managementList": "management",
    }
    for key, group_key in direct_group_map.items():
        for item in list_from_data(tam_data.get(key) or []):
            if isinstance(item, dict):
                groups[group_key].append(normalize_tam_metric(item))

    for outer_key, outer_value in tam_data.items():
        if not isinstance(outer_value, dict):
            continue
        group_key = parse_tam_group_key(outer_value.get("type") or outer_key)
        for item in list_from_data(outer_value.get("projectValueInfoList") or outer_value.get("valueInfoList") or []):
            if isinstance(item, dict):
                normalized_item = dict(item)
                if "type" not in normalized_item:
                    normalized_item["type"] = outer_value.get("type") or outer_key
                groups[group_key].append(normalize_tam_metric(normalized_item))

    for group_key, metrics in groups.items():
        deduped: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for metric in metrics:
            metric_id = normalize_text(metric.get("id") or metric.get("title"))
            if metric_id and metric_id in seen_ids:
                continue
            if metric_id:
                seen_ids.add(metric_id)
            deduped.append(metric)
        groups[group_key] = deduped
    return groups


def build_organization_members(*organization_sources: Any) -> tuple[list[dict[str, Any]], str]:
    members: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    own_count = 0
    third_count = 0

    for source in organization_sources:
        for item in list_from_data(source):
            if not isinstance(item, dict):
                continue
            name = (
                item.get("employeeName")
                or item.get("memberName")
                or item.get("userName")
                or item.get("name")
                or item.get("maintenanceName")
                or ""
            )
            role = item.get("postName") or item.get("roleName") or item.get("dutyName") or item.get("role") or ""
            level = item.get("rank") or item.get("levelName") or item.get("level") or ""
            workload = item.get("manDay") or item.get("workload") or ""
            if not any(str(value or "").strip() for value in [name, role, level, workload]):
                continue

            party_type = normalize_organization_party_type(item)
            if party_type == "third":
                third_count += 1
            else:
                own_count += 1

            member_id = normalize_text(
                item.get("id")
                or item.get("employeeId")
                or f"{name}|{role}|{item.get('planStartDate') or ''}|{item.get('planEndDate') or ''}|{party_type}"
            )
            if member_id in seen_ids:
                continue
            seen_ids.add(member_id)

            members.append(
                {
                    "name": name or ("三方资源" if party_type == "third" else ""),
                    "employee_id": item.get("employeeId") or item.get("userId") or "",
                    "role": role,
                    "level": level,
                    "department": item.get("department") or item.get("deptName") or "",
                    "department_id": item.get("departmentId") or item.get("deptId") or "",
                    "team_name": item.get("teamName") or item.get("groupName") or "",
                    "task_plan": item.get("taskDescription") or item.get("taskPlan") or "",
                    "workload": workload,
                    "plan_start_date": item.get("planStartDate") or item.get("startDate") or "",
                    "plan_end_date": item.get("planEndDate") or item.get("endDate") or "",
                    "party_type": party_type,
                    "flag": item.get("flag"),
                }
            )

    development_mode = ""
    if own_count and third_count:
        development_mode = "混合开发"
    elif own_count:
        development_mode = "自有人员"
    elif third_count:
        development_mode = "三方人员"
    return members, development_mode


def map_snapshot_to_document(snapshot: dict[str, Any], project_summary: dict[str, Any] | None, category: str) -> dict[str, Any]:
    summary = project_summary or {}
    endpoints = snapshot.get("endpoints", {})
    base_info = (endpoints.get("project_base_info") or {}).get("data") or {}

    upload_sections = extract_upload_sections((endpoints.get("project_uploading") or {}).get("data"))
    goal_data = normalize_goal_payload((endpoints.get("project_goal") or {}).get("data") or {})
    dev_scope_data = (endpoints.get("project_scope_dev") or {}).get("data") or {}
    ops_scope_primary_data = (endpoints.get("project_scope_ops") or {}).get("data") or {}
    ops_scope_get_scope_data = (endpoints.get("project_scope_ops_get_scope") or {}).get("data") or {}
    ops_scope_legacy_data = (endpoints.get("project_scope_ops_legacy") or {}).get("data") or {}
    ops_scope_data = pick_preferred_payload(ops_scope_primary_data, ops_scope_get_scope_data, ops_scope_legacy_data)
    system_scope_okr_data = (endpoints.get("system_scope_okr") or {}).get("data") or {}
    system_scope_data = pick_preferred_payload((endpoints.get("system_scope") or {}).get("data") or {}, system_scope_okr_data)
    tam_data = (endpoints.get("tam_info") or {}).get("data") or {}
    value_data = (endpoints.get("project_value") or {}).get("data") or {}
    milestone_data = (endpoints.get("milestones") or {}).get("data") or []
    org_data = (endpoints.get("organization") or {}).get("data") or {}
    org_framework_data = (endpoints.get("organization_framework") or {}).get("data") or {}
    org_flag_0_data = (endpoints.get("organization_flag_0") or {}).get("data") or {}
    org_flag_1_data = (endpoints.get("organization_flag_1") or {}).get("data") or {}
    budget_data = (endpoints.get("budget") or {}).get("data") or {}
    change_data = (endpoints.get("cost_change") or {}).get("data") or []

    milestones = {"approval_plan": {}, "contract_plan": {}, "target_plan": {}}
    for item in list_from_data(milestone_data):
        if not isinstance(item, dict):
            continue
        title = str(item.get("milestoneTitle", ""))
        bucket = map_milestone_bucket(title)
        if not bucket and str(item.get("okrFlag") or "").strip() == "1":
            bucket = "target_plan"
        if not bucket:
            continue
        milestones[bucket] = {
            "start": item.get("milestoneStartDate") or item.get("milestoneDate") or "",
            "end": item.get("milestoneDoneDate") or item.get("milestoneDate") or "",
            "title": title,
        }

    members, inferred_development_mode = build_organization_members(
        org_flag_0_data,
        org_flag_1_data,
        org_data,
        org_framework_data,
    )

    cost_items = []
    budget_items = list_from_data(budget_data.get("partInfos") if isinstance(budget_data, dict) else budget_data)
    for item in budget_items:
        if isinstance(item, dict) and any(key in item for key in ["budgetSubjectName", "partName", "name", "amount", "budgetName", "content", "expectFee"]):
            cost_items.append(
                {
                    "name": item.get("budgetName") or item.get("content") or item.get("partName") or item.get("name") or item.get("budgetSubjectName") or "budget_item",
                    "amount": item.get("expectFee") or item.get("budgetYearPrice") or item.get("partPrice") or item.get("amount") or item.get("budgetMoney") or item.get("proBudget") or "",
                    "budget_subject": item.get("budgetCode") or item.get("budgetSubjectName") or item.get("budgetName") or item.get("budgetTypeName") or "",
                    "calculation": item.get("calcMethod") or item.get("calculationBasis") or item.get("purchaseReason") or item.get("remark") or item.get("content") or "",
                    "purchase_mode": normalize_procurement_method(
                        item.get("purchaseModeName")
                        or item.get("purchaseMode")
                        or item.get("procurementMethodName")
                        or item.get("procurementMethod")
                    ),
                }
            )

    project_value_text = normalize_text(value_data)
    if isinstance(value_data, list):
        project_value_text = normalize_text(value_data[:5])

    reason = ""
    history_analysis = ""
    fixed_project = False
    history_rows, previous_projects, history_total_cost = extract_change_history_rows(change_data)
    for item in list_from_data(change_data):
        if not isinstance(item, dict):
            continue
        fixed_project = fixed_project or str(item.get("isChange")) == "1"
        reason = reason or normalize_text(item.get("changeReason") or item.get("analysis") or item.get("threeValue"))
        history_analysis = history_analysis or normalize_text(item)

    system_scope_rows = list_from_data(system_scope_data)
    if not system_scope_rows:
        system_scope_rows = build_system_scope_fallback(dev_scope_data)

    tam_models = extract_tam_models(tam_data)

    microservice_rows = system_scope_rows
    microapp_rows = [
        item
        for item in system_scope_rows
        if isinstance(item, dict) and str(item.get("type") or "").strip().lower() in {"app", "application", "microapp"}
    ]
    if not microapp_rows and microservice_rows:
        microapp_rows = microservice_rows

    scope_content_list = list_from_data(ops_scope_data)
    if not scope_content_list:
        scope_content_list = list_from_data(
            dev_scope_data.get("projectRange")
            or dev_scope_data.get("projectRangeFlowEntities")
            or dev_scope_data.get("projectRangeEaMapTreeEntities")
            or []
        )

    return {
        "project_name": first_non_empty(base_info.get("projectName"), summary.get("projectName"), snapshot.get("project_id"), "Remote Project"),
        "project_id": first_non_empty(base_info.get("id"), summary.get("id"), snapshot.get("project_id")),
        "category": category,
        "project_summary": {
            "project_name": first_non_empty(base_info.get("projectName"), summary.get("projectName"), snapshot.get("project_id"), "Remote Project"),
            "project_code": first_non_empty(base_info.get("projectCode"), base_info.get("serialNo"), summary.get("projectCode"), summary.get("serialNo")),
            "domain_name": first_non_empty(base_info.get("domainName"), base_info.get("belongTeamName"), summary.get("domainName"), summary.get("belongTeamName")),
            "department_name": first_non_empty(
                base_info.get("projectBusinessDepartmentName"),
                base_info.get("departmentName"),
                base_info.get("belongDepartmentName"),
                summary.get("departmentName"),
                summary.get("belongDepartmentName"),
            ),
            "project_manager_name": first_non_empty(
                base_info.get("managerName"),
                base_info.get("projectManagerName"),
                summary.get("managerName"),
                summary.get("projectManagerName"),
            ),
            "project_type_name": first_non_empty(
                base_info.get("projectTypeName"),
                base_info.get("projectFeeTypeName"),
                summary.get("projectTypeName"),
                summary.get("projectFeeTypeName"),
            ),
            "project_category_name": first_non_empty(
                base_info.get("projectCategoryName"),
                base_info.get("projectFeeTypeName"),
                summary.get("projectCategoryName"),
                summary.get("projectFeeTypeName"),
            ),
            "business_category_name": first_non_empty(
                base_info.get("projectClassifyParentName"),
                summary.get("businessCategoryName"),
                summary.get("projectCategoryName"),
            ),
            "business_subcategory_name": first_non_empty(
                base_info.get("projectClassifyName"),
                summary.get("businessSubcategoryName"),
                summary.get("projectTypeName"),
            ),
            "project_status_name": first_non_empty(
                base_info.get("projectStatusName"),
                summary.get("projectStatusName"),
                summary.get("projectStatus"),
                base_info.get("projectStatus"),
            ),
            "flow_status_name": first_non_empty(
                base_info.get("flowStatusName"),
                summary.get("flowStatusDisplay"),
                summary.get("flowStatusName"),
                summary.get("flowStatus"),
                base_info.get("flowStatus"),
            ),
            "fixed_project": first_non_empty(base_info.get("fixedProject"), summary.get("fixedProject")),
            "fixed_project_label": first_non_empty(base_info.get("fixedProjectLabel"), summary.get("fixedProjectLabel")),
            "project_level_name": first_non_empty(base_info.get("projectLevelName"), summary.get("projectLevelName")),
            "budget_year": first_non_empty(base_info.get("proBudgetYear"), base_info.get("proBudget"), summary.get("proBudgetYear"), summary.get("proBudget")),
        },
        "project_content": upload_sections,
        "okr": {
            "product_chain": goal_data.get("productLineName") or goal_data.get("productChainName") or "",
            "objective": goal_data.get("goalName") or goal_data.get("objective") or "",
            "squad_okr": goal_data.get("teamOkr") or goal_data.get("troopOkr") or "",
            "related_products": list_from_data(goal_data.get("relationProductList") or goal_data.get("productList") or []),
            "time_range": build_time_range(goal_data),
            "key_results": list_from_data(goal_data.get("krList") or goal_data.get("keyResults") or []),
        },
        "scope": {
            "business_processes": list_from_data(dev_scope_data.get("projectRangeFlowEntities") or dev_scope_data.get("projectRangeEaMapTreeEntities") or []),
            "content_list": scope_content_list,
            "microservices": microservice_rows,
            "microapps": microapp_rows,
        },
        "architecture_reviews": {
            "business": normalize_text(dev_scope_data.get("businessArchitecture") or ""),
            "data": normalize_text(dev_scope_data.get("dataArchitecture") or ""),
            "technology": normalize_text(dev_scope_data.get("technicalArchitecture") or ""),
            "security": normalize_text(dev_scope_data.get("securityArchitecture") or ""),
        },
        "tam_models": tam_models,
        "project_value": project_value_text,
        "milestones": milestones,
        "organization": {
            "development_mode": summary.get("developmentModeName") or inferred_development_mode,
            "members": members,
        },
        "budget": {
            "cost_items": cost_items,
        },
        "cost_change": {
            "fixed_project": fixed_project,
            "history_analysis": history_analysis,
            "reason": reason,
            "has_history_cost": bool(history_rows),
            "previous_projects": previous_projects,
            "history_total_cost": round(history_total_cost, 2) if history_total_cost else "",
            "history_items": history_rows,
        },
        "remote_snapshot": snapshot,
    }
