"""Split support helpers out of the main module for readability."""

from __future__ import annotations

from .remote_project_mapper_support import *  # noqa: F401,F403

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
    scope_line_data = (endpoints.get("project_scope_line") or {}).get("data") or {}
    scope_expense_detail_data = (endpoints.get("project_scope_expense_detail") or {}).get("data") or {}
    scope_expense_data = (endpoints.get("project_scope_expense") or {}).get("data") or {}
    scope_purchase_items_data = (endpoints.get("project_scope_purchase_items") or {}).get("data") or {}
    scope_machine_data = (endpoints.get("project_scope_machine") or {}).get("data") or {}
    scope_security_data = (endpoints.get("project_scope_security_data") or {}).get("data") or {}
    scope_security_list_data = (endpoints.get("project_scope_security_list") or {}).get("data") or {}
    scope_bus_add_data = (endpoints.get("project_scope_bus_add") or {}).get("data") or {}
    scope_bus_maintain_data = (endpoints.get("project_scope_bus_maintain") or {}).get("data") or {}
    merged_scope_rows = merge_payload_lists(
        ops_scope_primary_data,
        ops_scope_get_scope_data,
        ops_scope_legacy_data,
        scope_line_data,
        scope_expense_detail_data,
        scope_expense_data,
        scope_purchase_items_data,
        scope_machine_data,
        scope_security_data,
        scope_security_list_data,
        scope_bus_add_data,
        scope_bus_maintain_data,
    )
    ops_scope_data = merged_scope_rows or pick_preferred_payload(
        ops_scope_primary_data,
        ops_scope_get_scope_data,
        ops_scope_legacy_data,
        scope_line_data,
        scope_expense_detail_data,
        scope_expense_data,
        scope_purchase_items_data,
        scope_machine_data,
        scope_security_data,
        scope_security_list_data,
        scope_bus_add_data,
        scope_bus_maintain_data,
    )
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
    acceptance_task_info_data = (endpoints.get("acceptance_task_info") or {}).get("data") or {}
    acceptance_contract_info_data = (endpoints.get("acceptance_contract_info") or {}).get("data") or {}
    acceptance_info_list_data = (endpoints.get("acceptance_info_list") or {}).get("data") or {}
    acceptance_elements_data = (endpoints.get("acceptance_elements") or {}).get("data") or {}
    acceptance_stage_tasks_data = (endpoints.get("acceptance_stage_tasks") or {}).get("data") or []
    acceptance_stage_contracts_data = (endpoints.get("acceptance_stage_contracts") or {}).get("data") or []
    acceptance_count_data = (endpoints.get("acceptance_count_data") or {}).get("data") or []
    acceptance_architecture_elements_data = (endpoints.get("acceptance_architecture_elements") or {}).get("data") or []

    def flatten_acceptance_details(raw_value: Any) -> tuple[list[Any], list[str]]:
        rows: list[Any] = []
        accept_ids: list[str] = []
        for item in list_from_data(raw_value):
            if isinstance(item, dict) and "data" in item and ("acceptId" in item or "acceptid" in item):
                accept_id = normalize_text(first_non_empty(item.get("acceptId"), item.get("acceptid"), item.get("id")))
                if accept_id:
                    accept_ids.append(accept_id)
                for detail in list_from_data(item.get("data")):
                    if isinstance(detail, dict):
                        rows.append({
                            "acceptId": accept_id,
                            "acceptName": first_non_empty(item.get("acceptName"), item.get("name")),
                            **detail,
                        })
                    else:
                        rows.append(detail)
                continue
            rows.append(item)
        return rows, list(dict.fromkeys(accept_ids))

    def flatten_acceptance_scope_rows(raw_value: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in list_from_data(raw_value):
            if not isinstance(item, dict):
                continue
            if "data" in item and ("acceptId" in item or "acceptid" in item):
                accept_id = normalize_text(first_non_empty(item.get("acceptId"), item.get("acceptid"), item.get("id")))
                accept_name = normalize_text(first_non_empty(item.get("acceptName"), item.get("name")))
                nested_data = item.get("data")
                nested_rows = []
                if isinstance(nested_data, dict):
                    for key in ["newTaskList", "tasklist", "contractInfos", "dataList", "list", "rows", "records", "items"]:
                        value = nested_data.get(key)
                        if isinstance(value, list):
                            nested_rows.extend(value)
                else:
                    nested_rows.extend(list_from_data(nested_data))
                for detail in nested_rows:
                    if isinstance(detail, dict):
                        rows.append({"acceptId": accept_id, "acceptName": accept_name, **detail})
                continue
            rows.append(item)
        return rows

    acceptance_task_acceptance_rows, task_accept_ids = flatten_acceptance_details(acceptance_stage_tasks_data)
    acceptance_contract_acceptance_rows, contract_accept_ids = flatten_acceptance_details(acceptance_stage_contracts_data)
    acceptance_count_rows, count_accept_ids = flatten_acceptance_details(acceptance_count_data)
    acceptance_info_rows = list_from_data(acceptance_info_list_data)
    acceptance_task_rows = flatten_acceptance_scope_rows(acceptance_task_info_data)
    acceptance_contract_rows = flatten_acceptance_scope_rows(acceptance_contract_info_data)
    acceptance_element_rows = normalize_acceptance_architecture_items(acceptance_elements_data)
    acceptance_architecture_rows = normalize_acceptance_architecture_items(acceptance_architecture_elements_data)
    merged_acceptance_architecture_rows = acceptance_element_rows + [
        item
        for item in acceptance_architecture_rows
        if str(item.get("id") or "") not in {str(existing.get("id") or "") for existing in acceptance_element_rows}
    ]

    acceptance_ids = [
        *[
            normalize_text(first_non_empty(item.get("acceptId"), item.get("acceptid"), item.get("id")))
            for item in acceptance_info_rows
            if isinstance(item, dict)
        ],
        *task_accept_ids,
        *contract_accept_ids,
        *count_accept_ids,
    ]
    for item in [*acceptance_task_rows, *acceptance_contract_rows]:
        if isinstance(item, dict):
            accept_id = normalize_text(first_non_empty(item.get("acceptId"), item.get("acceptid"), item.get("accept_id")))
            if accept_id:
                acceptance_ids.append(accept_id)
    acceptance_ids = list(dict.fromkeys(acceptance_ids))
    acceptance_info_map = {
        normalize_text(first_non_empty(item.get("acceptId"), item.get("acceptid"), item.get("id"))): item
        for item in acceptance_info_rows
        if isinstance(item, dict)
    }

    def enrich_acceptance_rows(rows: list[Any]) -> list[Any]:
        enriched: list[Any] = []
        for item in rows:
            if not isinstance(item, dict):
                enriched.append(item)
                continue
            accept_id = normalize_text(first_non_empty(item.get("acceptId"), item.get("acceptid"), item.get("accept_id")))
            base = acceptance_info_map.get(accept_id) or {}
            enriched.append(
                {
                    **item,
                    "acceptId": accept_id,
                    "acceptName": first_non_empty(item.get("acceptName"), base.get("acceptName"), base.get("name"), base.get("id")),
                    "acceptStatusName": first_non_empty(item.get("acceptStatusName"), base.get("acceptStatusName"), base.get("projectStatus")),
                }
            )
        return enriched

    acceptance_task_rows = enrich_acceptance_rows(acceptance_task_rows)
    acceptance_contract_rows = enrich_acceptance_rows(acceptance_contract_rows)
    acceptance_task_acceptance_rows = enrich_acceptance_rows(acceptance_task_acceptance_rows)
    acceptance_contract_acceptance_rows = enrich_acceptance_rows(acceptance_contract_acceptance_rows)
    acceptance_count_rows = enrich_acceptance_rows(acceptance_count_rows)
    use_acceptance_deliverable_sample = should_use_acceptance_deliverable_sample(base_info, summary)
    standard_acceptance_deliverables = load_standard_acceptance_deliverables_sample(use_acceptance_deliverable_sample)
    task_acceptance_deliverables = load_task_acceptance_deliverables_sample(use_acceptance_deliverable_sample)

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
    change_items = extract_cost_change_metrics(change_data)
    for item in list_from_data(change_data):
        if not isinstance(item, dict):
            continue
        fixed_project = fixed_project or str(item.get("isChange")) == "1"
        reason = reason or normalize_text(item.get("changeReason") or item.get("analysis") or item.get("content"))
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

    scope_business_processes = list_from_data(
        dev_scope_data.get("projectRangeFlowEntities")
        or dev_scope_data.get("projectRangeEaMapTreeEntities")
        or []
    )
    if not scope_business_processes:
        scope_business_processes = list_from_data(ops_scope_data)

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
            "business_processes": scope_business_processes,
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
            "change_items": change_items,
        },
        "acceptance": {
            "acceptance_ids": acceptance_ids,
            "info_list": acceptance_info_rows,
            "task_list": acceptance_task_rows,
            "contract_list": acceptance_contract_rows,
            "task_acceptance_list": acceptance_task_acceptance_rows,
            "contract_acceptance_list": acceptance_contract_acceptance_rows,
            "deliverables": acceptance_count_rows,
            "standard_deliverables": standard_acceptance_deliverables,
            "task_deliverables": task_acceptance_deliverables,
            "architecture_elements": merged_acceptance_architecture_rows,
        },
        "remote_snapshot": snapshot,
    }
