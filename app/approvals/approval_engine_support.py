"""Deterministic approval engine for project-approval reviews."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.approvals.category_aliases import canonical_category_name, canonical_review_point
from app.core.paths import (
    CONFIG_PATH,
    LEGACY_LATEST_APPROVAL_RESULT_PATH,
    LEGACY_PROJECT_BUNDLE_PATH,
    PROJECT_ROOT,
    PROJECT_BUNDLE_PATH,
    SAMPLE_INPUT_PATH,
    SCRIPTS_DIR,
    scene_latest_approval_result_path,
    scene_skill_manifest_path,
    find_task_order_rule_matrix_path,
)
from app.core.scenes import normalize_scene

import sys

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_project_approval_bundle import load_or_create_config  # noqa: E402
from extract_review_rules import parse_rule_bundle  # noqa: E402

SEVERITY_WEIGHTS = {"critical": 12, "major": 7, "minor": 3}
CORE_CATEGORIES = {"工作台开发及实施", "产品运营", "系统产品购买"}
SYSTEM_DEVELOPMENT_CATEGORY_KEYWORDS = ("系统开发", "系统研发", "工作台开发", "系统开发及实施", "系统开发与实施")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rule_sequence_from_id(rule_id: str, fallback: int) -> str:
    digits = "".join(character for character in str(rule_id or "") if character.isdigit())
    if digits:
        return str(int(digits))
    return str(fallback)


def load_rules_bundle_from_manifest(scene: str) -> dict[str, Any]:
    manifest_path = scene_skill_manifest_path(scene)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Skill manifest does not exist: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    skills = payload.get("skills") or []
    if not isinstance(skills, list):
        skills = []

    categories_to_group: dict[str, str] = {}
    rules_by_id: dict[str, dict[str, Any]] = {}
    tab_counter: dict[str, int] = {}
    model_counter: dict[str, int] = {}
    dimension_counter: dict[str, int] = {}
    review_point_counter: dict[str, int] = {}
    category_counter: dict[str, int] = {}

    for skill in skills:
        if not isinstance(skill, dict):
            continue
        tab_name = str(skill.get("tab") or skill.get("review_point") or "").strip()
        model_name = str((skill.get("model_dimensions") or [""])[0] or "").strip()
        dimension_name = str((skill.get("dimensions") or [""])[0] or "").strip()
        default_group = str((skill.get("group_names") or ["manifest"])[0] or "manifest").strip()
        skill_categories = [str(item).strip() for item in (skill.get("categories") or []) if str(item).strip()]
        for category in skill_categories:
            categories_to_group.setdefault(category, default_group)

        for rule in skill.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("rule_id") or "").strip()
            if not rule_id:
                continue

            rule_categories = [str(item).strip() for item in (rule.get("categories") or skill_categories) if str(item).strip()]
            for category in rule_categories:
                category_counter[category] = category_counter.get(category, 0) + 1

            applicable_categories = [
                {"group": categories_to_group.get(category, default_group), "category": category}
                for category in rule_categories
            ]

            existing = rules_by_id.get(rule_id)
            if existing is None:
                sequence = _rule_sequence_from_id(rule_id, len(rules_by_id) + 1)
                normalized_rule = {
                    "rule_id": rule_id,
                    "sequence": str(rule.get("sequence") or sequence),
                    "tab": tab_name,
                    "model_dimension": str(rule.get("model_dimension") or model_name or "").strip(),
                    "dimension": str(rule.get("dimension") or dimension_name or "").strip(),
                    "review_point": str(rule.get("review_point") or tab_name or "").strip(),
                    "review_content": str(rule.get("review_content") or "").strip(),
                    "rule_text": str(rule.get("rule_text") or "").strip(),
                    "applicable_categories": applicable_categories,
                }
                rules_by_id[rule_id] = normalized_rule
                if normalized_rule["tab"]:
                    tab_counter[normalized_rule["tab"]] = tab_counter.get(normalized_rule["tab"], 0) + 1
                if normalized_rule["model_dimension"]:
                    model_counter[normalized_rule["model_dimension"]] = model_counter.get(normalized_rule["model_dimension"], 0) + 1
                if normalized_rule["dimension"]:
                    dimension_counter[normalized_rule["dimension"]] = dimension_counter.get(normalized_rule["dimension"], 0) + 1
                if normalized_rule["review_point"]:
                    review_point_counter[normalized_rule["review_point"]] = review_point_counter.get(normalized_rule["review_point"], 0) + 1
                continue

            if not existing.get("tab") and tab_name:
                existing["tab"] = tab_name
            if not existing.get("model_dimension") and model_name:
                existing["model_dimension"] = model_name
            if not existing.get("dimension") and dimension_name:
                existing["dimension"] = dimension_name
            if not existing.get("review_point") and rule.get("review_point"):
                existing["review_point"] = str(rule.get("review_point") or "").strip()
            if not existing.get("review_content") and rule.get("review_content"):
                existing["review_content"] = str(rule.get("review_content") or "").strip()
            if not existing.get("rule_text") and rule.get("rule_text"):
                existing["rule_text"] = str(rule.get("rule_text") or "").strip()

            existing_categories = {
                canonical_category_name(item.get("category"))
                for item in existing.get("applicable_categories") or []
                if isinstance(item, dict)
            }
            existing_applicable_categories = existing.get("applicable_categories")
            if not isinstance(existing_applicable_categories, list):
                existing_applicable_categories = []
                existing["applicable_categories"] = existing_applicable_categories
            for item in applicable_categories:
                normalized_category = canonical_category_name(item.get("category"))
                if normalized_category in existing_categories:
                    continue
                existing_applicable_categories.append(item)
                existing_categories.add(normalized_category)

    def _rule_sort_key(rule: dict[str, Any]) -> tuple[int, str]:
        sequence = _rule_sequence_from_id(str(rule.get("sequence") or rule.get("rule_id") or ""), 9999)
        return int(sequence), str(rule.get("rule_id") or "")

    sorted_rules = sorted(rules_by_id.values(), key=_rule_sort_key)

    categories = [
        {"column": f"M{index + 1}", "group": group, "name": category}
        for index, (category, group) in enumerate(sorted(categories_to_group.items(), key=lambda item: item[0]))
    ]

    return {
        "source": str(manifest_path),
        "sheet": "manifest",
        "categories": categories,
        "rules": sorted_rules,
        "summary": {
            "rule_count": len(sorted_rules),
            "category_count": len(categories),
            "by_tab": {key: value for key, value in sorted(tab_counter.items()) if key},
            "by_model_dimension": {key: value for key, value in sorted(model_counter.items()) if key},
            "by_dimension": {key: value for key, value in sorted(dimension_counter.items()) if key},
            "by_review_point": {key: value for key, value in sorted(review_point_counter.items()) if key},
            "by_category": dict(sorted(category_counter.items())),
        },
    }


def load_rules_bundle(scene: str = "initiation") -> dict[str, Any]:
    normalized_scene = normalize_scene(scene)
    if normalized_scene == "task_order":
        return parse_rule_bundle(find_task_order_rule_matrix_path())

    rules_bundle = load_rules_bundle_from_manifest(normalized_scene)
    if normalized_scene == "initiation":
        config = load_or_create_config(CONFIG_PATH, PROJECT_ROOT, rules_bundle)
        enabled_skill_groups = set(config.get("generation", {}).get("enabled_skill_groups", []))
        if enabled_skill_groups:
            rules_bundle["rules"] = [
                rule
                for rule in rules_bundle["rules"]
                if (rule.get("review_point") or "").strip() in enabled_skill_groups
            ]
    return rules_bundle


def load_generated_project_bundle() -> dict[str, Any]:
    path = PROJECT_BUNDLE_PATH
    if not path.exists() and LEGACY_PROJECT_BUNDLE_PATH.exists():
        path = LEGACY_PROJECT_BUNDLE_PATH
    if not path.exists():
        raise FileNotFoundError("generated/project_approval_project.json does not exist. Run /api/generate first.")
    return json.loads(path.read_text(encoding="utf-8"))


def get_value(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(normalize_text(item) for item in value if normalize_text(item))
    if isinstance(value, dict):
        return "\n".join(f"{key}:{normalize_text(item)}" for key, item in value.items() if normalize_text(item))
    return str(value).strip()


def normalize_list_like(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ["dataList", "list", "rows", "records", "items", "partInfos"]:
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
        return [value] if value else []
    return []


def first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict, tuple, set)) and not value:
            continue
        return value
    return ""


def normalize_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("，", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_lookup_key(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(char for char in text if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def build_task_order_review_context(document: dict[str, Any]) -> dict[str, Any]:
    summary = document.get("project_summary") or {}
    milestones = document.get("milestones") or {}
    scope = document.get("scope") or {}
    organization = document.get("organization") or {}
    project_content = document.get("project_content") or {}
    okr = document.get("okr") or {}
    budget = document.get("budget") or {}
    cost_change = document.get("cost_change") or {}
    architecture_reviews = document.get("architecture_reviews") or {}

    related_products = [
        first_present(
            item.get("productName") if isinstance(item, dict) else None,
            item.get("productFullName") if isinstance(item, dict) else None,
            item.get("name") if isinstance(item, dict) else None,
            item.get("label") if isinstance(item, dict) else None,
            item,
        )
        for item in normalize_list_like(okr.get("related_products"))
    ]
    related_products = [str(item).strip() for item in related_products if str(item or "").strip()]

    key_results = [
        first_present(
            item.get("krName") if isinstance(item, dict) else None,
            item.get("name") if isinstance(item, dict) else None,
            item.get("title") if isinstance(item, dict) else None,
            item.get("description") if isinstance(item, dict) else None,
            item,
        )
        for item in normalize_list_like(okr.get("key_results"))
    ]
    key_results = [str(item).strip() for item in key_results if str(item or "").strip()]
    project_goals = [str(item).strip() for item in [okr.get("objective"), *key_results] if str(item or "").strip()]

    start_date = first_present(
        (milestones.get("target_plan") or {}).get("start") if isinstance(milestones.get("target_plan"), dict) else None,
        (milestones.get("approval_plan") or {}).get("start") if isinstance(milestones.get("approval_plan"), dict) else None,
        (milestones.get("contract_plan") or {}).get("start") if isinstance(milestones.get("contract_plan"), dict) else None,
    )
    end_date = first_present(
        (milestones.get("target_plan") or {}).get("end") if isinstance(milestones.get("target_plan"), dict) else None,
        (milestones.get("approval_plan") or {}).get("end") if isinstance(milestones.get("approval_plan"), dict) else None,
        (milestones.get("contract_plan") or {}).get("end") if isinstance(milestones.get("contract_plan"), dict) else None,
    )

    members = normalize_list_like(organization.get("members"))
    supplier_name = first_present(
        next((item.get("name") for item in members if isinstance(item, dict) and item.get("party_type") == "third" and str(item.get("name") or "").strip()), ""),
        members[0].get("name") if members and isinstance(members[0], dict) else "",
        summary.get("project_manager_name"),
    )

    cost_items = normalize_list_like(budget.get("cost_items"))
    contract_name = first_present(
        cost_items[0].get("name") if cost_items and isinstance(cost_items[0], dict) else "",
        f"{summary.get('project_name') or document.get('project_name') or '项目'}任务执行合同",
    )
    contract_no = first_present(summary.get("project_code"), document.get("project_id"), "TASK-CONTRACT")

    business_units = []
    for index, item in enumerate(normalize_list_like(scope.get("content_list"))[:8]):
        if not isinstance(item, dict):
            item = {"name": item}
        business_units.append(
            {
                "business_object": first_present(item.get("businessObjectName"), item.get("businessObject"), item.get("name"), item.get("systemName"), f"业务对象{index + 1}"),
                "business_unit": first_present(item.get("businessUnitName"), item.get("lineName"), item.get("typeName"), item.get("categoryName"), f"业务单元{index + 1}"),
                "business_process": first_present(item.get("processName"), item.get("flowName"), item.get("content"), item.get("description"), item.get("name"), f"业务流程{index + 1}"),
            }
        )

    business_processes = normalize_list_like(scope.get("business_processes"))
    microservices = normalize_list_like(scope.get("microservices"))
    approval_nodes = [
        {
            "function_name": "业务架构核对",
            "removed_nodes": 1 if business_processes else 0,
            "description": "已识别业务过程，可沉淀标准任务流。" if business_processes else "待补充业务过程后生成审批优化建议。",
        },
        {
            "function_name": "数据与系统核对",
            "removed_nodes": 1 if microservices else 0,
            "description": "已识别系统范围，可收敛人工确认节点。" if microservices else "待补充系统范围与接口要求。",
        },
    ]

    process_rows = []
    for index, item in enumerate(business_processes[:8]):
        if not isinstance(item, dict):
            item = {"name": item}
        process_rows.append(
            {
                "process_name": first_present(item.get("name"), item.get("processName"), item.get("code"), f"业务流程{index + 1}"),
                "process_code": first_present(item.get("code"), item.get("processCode"), item.get("id"), f"P-{index + 1}"),
                "owner": first_present(summary.get("project_manager_name"), supplier_name, "待补充"),
                "output": first_present(item.get("futureTime"), item.get("actualTime"), item.get("type"), "阶段输出"),
            }
        )

    source_rows = process_rows or business_units
    task_rows = []
    for index, item in enumerate(source_rows[:6]):
        task_rows.append(
            {
                "task_name": first_present(item.get("process_name"), item.get("business_process"), item.get("business_object"), f"任务{index + 1}"),
                "task_owner": first_present(summary.get("project_manager_name"), supplier_name, "待补充"),
                "deliverable": first_present(item.get("output"), item.get("business_unit"), "任务交付物"),
                "complete_standard": key_results[index] if index < len(key_results) else "完成任务范围并通过阶段确认",
            }
        )

    metric_rows = [
        {"metric_name": item, "metric_type": "项目指标", "target_value": "达成"}
        for item in key_results
    ]

    staffing_rows = []
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            continue
        expected_days = normalize_number(member.get("workload"))
        unit_price = 1800 if member.get("party_type") == "third" else 1200
        staffing_rows.append(
            {
                "name": member.get("name") or f"成员{index + 1}",
                "post_name": member.get("role") or "实施角色",
                "level_name": member.get("level") or "待补充",
                "expected_days": expected_days or "",
                "unit_price": unit_price,
                "estimated_cost": expected_days * unit_price if expected_days else "",
                "department_name": member.get("department") or summary.get("department_name") or "",
                "start_date": member.get("plan_start_date") or start_date,
                "end_date": member.get("plan_end_date") or end_date,
            }
        )

    current_cost_rows = [
        {
            "post_name": item.get("post_name"),
            "level_name": item.get("level_name"),
            "expected_days": item.get("expected_days"),
            "unit_price": item.get("unit_price"),
            "estimated_cost": item.get("estimated_cost"),
        }
        for item in staffing_rows
    ]
    history_rows = []
    for index, item in enumerate(normalize_list_like(cost_change.get("history_items"))):
        if not isinstance(item, dict):
            item = {"name": item}
        history_rows.append(
            {
                "task_name": first_present(item.get("projectName"), item.get("taskName"), item.get("name"), f"历史任务单{index + 1}"),
                "task_code": first_present(item.get("projectCode"), item.get("taskNo"), item.get("code"), f"H-{index + 1}"),
                "total_cost": first_present(item.get("totalCost"), item.get("amount"), item.get("cost"), ""),
                "status": first_present(item.get("status"), item.get("projectStatusName"), "已完成"),
            }
        )

    total_days = sum(normalize_number(item.get("expected_days")) for item in staffing_rows)
    total_cost = sum(normalize_number(item.get("estimated_cost")) for item in current_cost_rows)
    history_total_cost = sum(normalize_number(item.get("total_cost")) for item in history_rows)
    project_budget_amount = total_cost or normalize_number(cost_items[0].get("amount") if cost_items and isinstance(cost_items[0], dict) else 0)

    technical_requirements = {
        "系统功能需求": first_present((project_content.get("solution") or {}).get("content") if isinstance(project_content.get("solution"), dict) else "", document.get("project_value"), okr.get("objective")),
        "系统架构需求": first_present(architecture_reviews.get("technology"), architecture_reviews.get("business")),
        "系统集成与接口要求": f"需对接 {len(microservices)} 个系统/微应用对象。" if microservices else "",
        "数据库要求": first_present(architecture_reviews.get("data"), cost_items[0].get("budget_subject") if cost_items and isinstance(cost_items[0], dict) else ""),
        "性能要求": f"需在 {start_date} 至 {end_date} 内完成交付。" if start_date and end_date else "",
        "安全性要求": first_present(architecture_reviews.get("security"), (project_content.get("acceptance_plan") or {}).get("content") if isinstance(project_content.get("acceptance_plan"), dict) else ""),
        "扩展性要求": f"已识别 {len(normalize_list_like(scope.get('content_list')))} 条范围内容，需保留扩展余量。" if normalize_list_like(scope.get("content_list")) else "",
        "技术栈要求": first_present(summary.get("project_type_name"), summary.get("business_subcategory_name")),
        "前端设计要求": first_present((project_content.get("panorama") or {}).get("content") if isinstance(project_content.get("panorama"), dict) else "", (project_content.get("solution") or {}).get("content") if isinstance(project_content.get("solution"), dict) else ""),
        "兼容性要求": "需兼容现有微应用和系统范围。" if normalize_list_like(scope.get("microapps")) else "",
        "质量要求": f"当前任务拆分 {len(task_rows)} 项，需逐项验收闭环。" if task_rows else "",
        "进度要求": first_present((milestones.get("target_plan") or {}).get("title") if isinstance(milestones.get("target_plan"), dict) else "", (milestones.get("approval_plan") or {}).get("title") if isinstance(milestones.get("approval_plan"), dict) else ""),
        "交接维保要求": first_present((project_content.get("target") or {}).get("content") if isinstance(project_content.get("target"), dict) else "", cost_change.get("reason")),
        "交接物明细": "、".join(related_products),
        "项目验收条件": "；".join(project_goals),
    }

    return {
        "basic_info": {
            "任务单名称": f"{summary.get('project_name') or document.get('project_name') or '项目'}任务单",
            "任务单编号": f"{first_present(summary.get('project_code'), document.get('project_id'), 'TASK')}-001",
            "开始时间": start_date,
            "结束时间": end_date,
            "供应商": supplier_name,
            "合同名称": contract_name,
            "合同编号": contract_no,
            "项目目标": project_goals,
            "产品名称": related_products,
            "选择供应商原因": first_present(cost_change.get("reason"), document.get("project_value")),
            "采购说明": first_present((project_content.get("solution") or {}).get("content") if isinstance(project_content.get("solution"), dict) else "", (project_content.get("target") or {}).get("content") if isinstance(project_content.get("target"), dict) else ""),
        },
        "business_architecture": {
            "业务单元清单": business_units,
            "审批节点": approval_nodes,
        },
        "task_assignment": {
            "业务流程列表": process_rows,
            "任务列表（必填）": task_rows,
            "指标列表（非必填）": metric_rows,
        },
        "staffing": {
            "岗位、职级、预计人天、人员单价、预计费用": staffing_rows,
            "预计费用": total_cost,
        },
        "cost_estimation": {
            "岗位、职级、人天、单价、费用": current_cost_rows,
            "历史任务单明细": history_rows,
            "本次任务单费用": total_cost,
            "历史任务单费用": history_total_cost or normalize_number(cost_change.get("history_total_cost")),
        },
        "technical_requirements": technical_requirements,
        "project_budget": project_budget_amount,
    }


def normalize_category_key(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(character for character in text if character.isalnum())


def metric_is_complete(metric: dict[str, Any]) -> bool:
    required = ["title", "current_state", "benefit_department", "target_3y", "calculation_basis"]
    return all(is_present(metric.get(field)) for field in required)


def is_system_development_project(document: dict[str, Any], category: str) -> bool:
    summary = get_value(document, "project_summary") or {}
    candidates = [
        category,
        summary.get("business_subcategory_name"),
        summary.get("business_category_name"),
        summary.get("project_type_name"),
        summary.get("project_category_name"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if any(keyword in text for keyword in SYSTEM_DEVELOPMENT_CATEGORY_KEYWORDS):
            return True
    return False


def milestone_complete(milestone: Any) -> bool:
    if isinstance(milestone, dict):
        return is_present(milestone.get("start")) and is_present(milestone.get("end"))
    return is_present(milestone)


def select_active_rules(rules_bundle: dict[str, Any], category: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    normalized_category = normalize_category_key(canonical_category_name(category))
    for rule in rules_bundle["rules"]:
        if not rule["review_content"] and not rule["rule_text"]:
            continue
        applicable_categories = {
            normalize_category_key(canonical_category_name(item["category"]))
            for item in rule["applicable_categories"]
        }
        if applicable_categories and normalized_category not in applicable_categories:
            continue
        selected.append(rule)
    return selected


def default_suggestion(rule: dict[str, Any]) -> str:
    if rule["rule_text"]:
        return rule["rule_text"].splitlines()[0]
    return f"补充 {rule['review_point']} - {rule['review_content']} 的相关材料。"


def severity_for_rule(rule: dict[str, Any]) -> str:
    review_content = rule["review_content"]
    review_point = canonical_review_point(rule["review_point"])
    if review_content in {"背景图片", "目标图片", "方案图片", "业务全景图图片", "管理模型图片"}:
        return "minor"
    if review_point in {"专业领域评审", "能力（竞争）模型", "结果（财务/客户）模型", "管理体系模型", "费用变化点"}:
        return "major"
    if review_point in {"项目价值", "项目里程碑", "组织架构", "费用构成"}:
        return "critical"
    if review_content == "不需要":
        return "minor"
    return "critical"


def _legacy_evaluate_title_content_image_old(section: dict[str, Any], review_content: str) -> tuple[bool, str]:
    mapping = {
        "背景标题": ("title", "缺少背景标题"),
        "背景内容": ("content", "缺少背景内容"),
        "背景图片": ("images", "缺少背景图片"),
        "项目目标": ("title", "缺少项目目标标题"),
        "项目内容": ("content", "缺少项目目标内容"),
        "目标图片": ("images", "缺少目标图片"),
        "项目方案": ("title", "缺少方案标题"),
        "方案内容": ("content", "缺少方案内容"),
        "方案图片": ("images", "缺少方案图片"),
        "业务全景图标题": ("title", "缺少业务全景图标题"),
        "业务全景图内容": ("content", "缺少业务全景图内容"),
        "业务全景图图片": ("images", "缺少业务全景图图片"),
        "管理模型标题": ("title", "缺少管理模型标题"),
        "管理模型内容": ("content", "缺少管理模型内容"),
        "管理模型图片": ("images", "缺少管理模型图片"),
    }
    field_name, missing_message = mapping[review_content]
    value = section.get(field_name)
    if not is_present(value):
        return False, missing_message
    if field_name == "content":
        text = normalize_text(value)
        if len(text) < 20:
            return False, f"{review_content}过短，无法支撑审批。"
    return True, "材料完整"


def evaluate_title_content_image(section: dict[str, Any], review_content: str) -> tuple[bool, str]:
    mapping = {
        "背景标题": ("title", "缺少背景标题"),
        "背景内容": ("content", "缺少背景内容"),
        "背景图片": ("images", "缺少背景图片"),
        "项目目标": ("title", "缺少项目目标标题"),
        "项目内容": ("content", "缺少项目目标内容"),
        "目标图片": ("images", "缺少目标图片"),
        "项目方案": ("title", "缺少方案标题"),
        "方案内容": ("content", "缺少方案内容"),
        "方案图片": ("images", "缺少方案图片"),
        "业务全景图标题": ("title", "缺少业务全景图标题"),
        "业务全景图内容": ("content", "缺少业务全景图内容"),
        "业务全景图图片": ("images", "缺少业务全景图图片"),
        "管理模型标题": ("title", "缺少管理模型标题"),
        "管理模型内容": ("content", "缺少管理模型内容"),
        "管理模型图片": ("images", "缺少管理模型图片"),
        "验收方案标题": ("title", "缺少验收方案标题"),
        "验收方案内容": ("content", "缺少验收方案内容"),
        "验收方案图片": ("images", "缺少验收方案图片"),
    }
    field_name, missing_message = mapping.get(review_content, ("content", f"缺少{review_content}"))
    value = section.get(field_name)
    if not is_present(value):
        return False, missing_message
    if field_name == "content":
        text = normalize_text(value)
        if len(text) < 20:
            return False, f"{review_content}过短，无法支撑审批。"
    return True, "材料完整"


def section_marked_not_involved(section: Any) -> bool:
    markers = ("不涉及", "不适用", "无需", "not involved", "not applicable", "n/a")

    def has_marker(value: Any) -> bool:
        text = normalize_text(value)
        if not text:
            return False
        lowered = text.lower()
        return any(marker in text or marker in lowered for marker in markers)

    if has_marker(section):
        return True
    if not isinstance(section, dict):
        return False
    candidate_values = [
        section.get("title"),
        section.get("content"),
        section.get("conclusion"),
        section.get("reviewConclusion"),
        section.get("status"),
        section.get("statusName"),
    ]
    for item in normalize_list_like(section.get("items")):
        if isinstance(item, dict):
            candidate_values.extend(
                [
                    item.get("title"),
                    item.get("content"),
                    item.get("conclusion"),
                    item.get("reviewConclusion"),
                    item.get("status"),
                    item.get("statusName"),
                ]
            )
        else:
            candidate_values.append(item)
    return any(has_marker(value) for value in candidate_values)


def evaluate_acceptance_pair_rule(
    rule: dict[str, Any],
    acceptance: dict[str, Any],
    review_point: str,
    review_content: str,
) -> tuple[bool, str, str]:
    normalized_point = normalize_lookup_key(review_point)
    task_point = normalize_lookup_key("任务单")
    contract_point = normalize_lookup_key("合同")
    if normalized_point not in {task_point, contract_point}:
        return False, "", ""

    normalized_content = normalize_lookup_key(review_content)
    uses_acceptance_rows = "验收" in normalized_content and "展示" not in normalized_content and "清单" not in normalized_content
    primary_label = "任务单" if normalized_point == task_point else "合同"
    counterpart_label = "合同" if primary_label == "任务单" else "任务单"
    primary_keys = (
        ["task_acceptance_list", "task_list"]
        if primary_label == "任务单" and uses_acceptance_rows
        else ["task_list", "task_acceptance_list"]
        if primary_label == "任务单"
        else ["contract_acceptance_list", "contract_list"]
        if uses_acceptance_rows
        else ["contract_list", "contract_acceptance_list"]
    )
    counterpart_keys = (
        ["contract_acceptance_list", "contract_list"]
        if primary_label == "任务单" and uses_acceptance_rows
        else ["contract_list", "contract_acceptance_list"]
        if primary_label == "任务单"
        else ["task_acceptance_list", "task_list"]
        if uses_acceptance_rows
        else ["task_list", "task_acceptance_list"]
    )

    primary_value = first_present(*(acceptance.get(key) for key in primary_keys))
    if is_present(primary_value):
        return True, f"{primary_label}材料完整", normalize_text(primary_value)

    counterpart_value = first_present(*(acceptance.get(key) for key in counterpart_keys))
    any_of_one_rule = "三者有一" in str(rule.get("rule_text") or "") or "验收" in normalized_content
    if any_of_one_rule and is_present(counterpart_value):
        return True, f"已提供{counterpart_label}信息，按验收规则“有其一即可”视为满足", normalize_text(counterpart_value)

    return False, f"缺少{review_content}", normalize_text(primary_value)


