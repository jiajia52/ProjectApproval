"""Deterministic approval engine for project-approval reviews."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.approvals.category_aliases import canonical_category_name, canonical_review_point
from app.core.paths import CONFIG_PATH, GENERATED_DIR, PROJECT_ROOT, SAMPLE_INPUT_PATH, SCRIPTS_DIR, find_rule_matrix_path

import sys

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_project_approval_bundle import load_or_create_config, resolve_rule_matrix_path  # noqa: E402
from extract_review_rules import parse_rule_bundle  # noqa: E402

SEVERITY_WEIGHTS = {"critical": 12, "major": 7, "minor": 3}
CORE_CATEGORIES = {"工作台开发及实施", "产品运营", "系统产品购买"}
SYSTEM_DEVELOPMENT_CATEGORY_KEYWORDS = ("系统开发", "系统研发", "工作台开发", "系统开发及实施", "系统开发与实施")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_rules_bundle() -> dict[str, Any]:
    bootstrap_rules = parse_rule_bundle(find_rule_matrix_path())
    config = load_or_create_config(CONFIG_PATH, PROJECT_ROOT, bootstrap_rules)
    rules_bundle = parse_rule_bundle(resolve_rule_matrix_path(PROJECT_ROOT, config))
    enabled_skill_groups = set(config.get("generation", {}).get("enabled_skill_groups", []))
    if enabled_skill_groups:
        rules_bundle["rules"] = [
            rule
            for rule in rules_bundle["rules"]
            if (rule.get("review_point") or "").strip() in enabled_skill_groups
        ]
    return rules_bundle


def load_generated_project_bundle() -> dict[str, Any]:
    path = GENERATED_DIR / "project_approval_project.json"
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


def evaluate_rule(rule: dict[str, Any], document: dict[str, Any], category: str) -> dict[str, Any]:
    review_point = canonical_review_point(rule["review_point"])
    review_content = rule["review_content"]
    severity = severity_for_rule(rule)
    evidence = ""
    passed = False
    message = ""

    if review_content == "不需要":
        return {
            "rule_id": rule["rule_id"],
            "review_point": review_point,
            "review_content": review_content,
            "status": "pass",
            "severity": "minor",
            "message": "该规则标记为不需要。",
            "suggestion": "无需补充此项。",
            "evidence": "",
        }

    content_sections = get_value(document, "project_content") or {}
    okr = get_value(document, "okr") or {}
    scope = get_value(document, "scope") or {}
    architecture = get_value(document, "architecture_reviews") or {}
    tam_models = get_value(document, "tam_models") or {}
    milestones = get_value(document, "milestones") or {}
    organization = get_value(document, "organization") or {}
    budget = get_value(document, "budget") or {}
    cost_change = get_value(document, "cost_change") or {}
    project_value = get_value(document, "project_value")
    system_development_project = is_system_development_project(document, category)

    if review_point == "项目背景":
        passed, message = evaluate_title_content_image(content_sections.get("background") or {}, review_content)
        evidence = normalize_text(content_sections.get("background") or {})
    elif review_point == "项目目标":
        passed, message = evaluate_title_content_image(content_sections.get("target") or {}, review_content)
        evidence = normalize_text(content_sections.get("target") or {})
    elif review_point == "项目方案":
        passed, message = evaluate_title_content_image(content_sections.get("solution") or {}, review_content)
        evidence = normalize_text(content_sections.get("solution") or {})
    elif review_point == "业务全景图":
        if system_development_project:
            passed = True
            message = "系统开发项目不要求业务全景图"
            evidence = "exempt_for_system_development_project"
        else:
            passed, message = evaluate_title_content_image(content_sections.get("panorama") or {}, review_content)
            evidence = normalize_text(content_sections.get("panorama") or {})
    elif review_point == "年度管理模型":
        if system_development_project:
            passed = True
            message = "系统开发项目不要求年度管理模型"
            evidence = "exempt_for_system_development_project"
        else:
            passed, message = evaluate_title_content_image(content_sections.get("annual_model") or {}, review_content)
            evidence = normalize_text(content_sections.get("annual_model") or {})
    elif review_point == "项目OKR":
        okr_mapping = {
            "关联产品链": okr.get("product_chain"),
            "项目目标（O）": okr.get("objective"),
            "战队OKR": okr.get("squad_okr"),
            "关联产品": okr.get("related_products"),
            "目标时间范围": okr.get("time_range"),
            "关键成果（KR）": okr.get("key_results"),
        }
        value = okr_mapping.get(review_content)
        passed = is_present(value)
        if review_content == "目标时间范围" and isinstance(value, dict):
            passed = is_present(value.get("start")) and is_present(value.get("end"))
        if review_content == "关键成果（KR）" and isinstance(value, list):
            passed = len([item for item in value if normalize_text(item)]) > 0
        message = "OKR材料完整" if passed else f"缺少或未明确 {review_content}"
        evidence = normalize_text(value)
    elif review_point == "项目范围":
        value = scope.get("business_processes") if review_content == "业务流程" else scope.get("content_list")
        passed = is_present(value)
        message = "范围材料完整" if passed else f"缺少 {review_content}"
        evidence = normalize_text(value)
    elif review_point == "系统范围":
        value = scope.get("microservices") if review_content == "微服务" else scope.get("microapps")
        passed = is_present(value)
        message = "系统范围完整" if passed else f"缺少 {review_content}"
        evidence = normalize_text(value)
    elif review_point == "专业领域评审":
        field_map = {
            "业务架构评审": "business",
            "数据架构评审": "data",
            "技术架构评审": "technology",
            "安全架构评审": "security",
        }
        value = architecture.get(field_map[review_content])
        passed = is_present(value)
        message = "架构评审材料完整" if passed else f"缺少 {review_content}"
        evidence = normalize_text(value)
    elif review_point in {"能力（竞争）模型", "结果（财务/客户）模型", "管理体系模型"}:
        field_map = {
            "能力（竞争）模型": "capability",
            "结果（财务/客户）模型": "result",
            "管理体系模型": "management",
        }
        metrics = tam_models.get(field_map[review_point]) or []
        passed = any(
            metric_is_complete(metric)
            for group_metrics in tam_models.values()
            for metric in (group_metrics or [])
            if isinstance(metric, dict)
        )
        message = "TAM 模型指标完整" if passed else f"{review_point}缺少完整指标。"
        evidence = normalize_text(metrics)
    elif review_point == "项目价值":
        passed = is_present(project_value)
        message = "项目价值已填写" if passed else "缺少项目价值说明"
        evidence = normalize_text(project_value)
    elif review_point == "项目里程碑":
        field_map = {"立项计划": "approval_plan", "合同计划": "contract_plan", "目标计划": "target_plan"}
        value = milestones.get(field_map[review_content])
        passed = milestone_complete(value)
        message = "里程碑计划完整" if passed else f"{review_content}缺少完整时间范围"
        evidence = normalize_text(value)
    elif review_point == "组织架构":
        members = organization.get("members") or []
        mode = organization.get("development_mode")
        normalized_members = [member for member in members if isinstance(member, dict)]
        members_complete = len(normalized_members) > 0 and all(
            is_present(member.get("name")) and is_present(member.get("role"))
            for member in normalized_members
        )
        if category in CORE_CATEGORIES or system_development_project:
            passed = members_complete and is_present(mode)
            message = "组织架构完整" if passed else "组织成员或开发模式不完整"
        else:
            passed = members_complete
            message = "组织架构完整" if passed else "组织成员信息不完整"
        evidence = normalize_text(organization)
    elif review_point == "费用构成":
        items = budget.get("cost_items") or []
        passed = len(items) > 0 and all(
            is_present(item.get("name"))
            and is_present(item.get("amount"))
            and is_present(item.get("budget_subject"))
            and is_present(item.get("calculation"))
            and is_present(item.get("purchase_mode"))
            for item in items
            if isinstance(item, dict)
        )
        message = "费用构成完整" if passed else "预算成本项、测算或采购方式不完整"
        evidence = normalize_text(items)
    elif review_point == "费用变化点":
        fixed_project = bool(cost_change.get("fixed_project"))
        if fixed_project:
            passed = is_present(cost_change.get("history_analysis")) and is_present(cost_change.get("reason"))
            message = "固定类项目费用变化说明完整" if passed else "固定类项目缺少历史费用分析或变化原因"
        else:
            passed = is_present(cost_change.get("reason")) or not fixed_project
            message = "费用变化点已说明" if passed else "缺少费用变化点说明"
        evidence = normalize_text(cost_change)
    elif review_point == "长尾费用":
        passed = True
        message = "当前规则标记为不需要。"
    elif review_point == "历史投入":
        passed = True
        message = "当前规则标记为不需要。"
    else:
        passed = False
        message = f"未实现的规则映射: {review_point}/{review_content}"

    return {
        "rule_id": rule["rule_id"],
        "review_point": review_point,
        "review_content": review_content,
        "status": "pass" if passed else "fail",
        "severity": severity,
        "message": message,
        "suggestion": default_suggestion(rule),
        "evidence": evidence[:400],
    }


def summarize_results(category: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    findings = [item for item in results if item["status"] == "fail"]
    critical = [item for item in findings if item["severity"] == "critical"]
    major = [item for item in findings if item["severity"] == "major"]
    minor = [item for item in findings if item["severity"] == "minor"]
    passed = [item for item in results if item["status"] == "pass"]

    score = max(
        0,
        100
        - len(critical) * SEVERITY_WEIGHTS["critical"]
        - len(major) * SEVERITY_WEIGHTS["major"]
        - len(minor) * SEVERITY_WEIGHTS["minor"],
    )

    if critical:
        decision = "驳回"
    elif major or minor:
        decision = "需补充材料"
    else:
        decision = "通过"

    return {
        "category": category,
        "decision": decision,
        "score": score,
        "statistics": {
            "total_rules": len(results),
            "passed_rules": len(passed),
            "failed_rules": len(findings),
            "critical_failures": len(critical),
            "major_failures": len(major),
            "minor_failures": len(minor),
        },
        "findings": findings,
    }


def build_sample_approval_document(category: str = "工作台开发及实施") -> dict[str, Any]:
    return {
        "project_name": "项目立项自动审批系统",
        "category": category,
        "project_content": {
            "background": {
                "title": "现状与痛点分析",
                "content": "当前立项审批依赖人工审核，存在周期长、规则不统一、数据分散获取困难等现状与痛点，本项目目标是打通接口、统一规则并实现审批自动化范围覆盖。",
                "images": ["background-current-state.png"],
            },
            "target": {
                "title": "项目建设目标",
                "content": "目标直接对应业务价值，要求审批周期缩短、结果可追溯、规则统一落地，并定义明确完成标准和年度目标。",
                "images": ["target-metrics.png"],
            },
            "solution": {
                "title": "实施方案总览",
                "content": "方案包括接口接入层、规则引擎层、审批应用层和前端配置层，覆盖数据获取、规则校验、结果生成与追溯。",
                "images": ["solution-architecture.png"],
            },
            "panorama": {
                "title": "业务全景图",
                "content": "业务全景图覆盖从战略目标到审批人、立项人和系统管理员的用户价值闭环，明确流程节点与收益链路。",
                "images": ["business-panorama.png"],
            },
            "annual_model": {
                "title": "年度管理模型",
                "content": "年度管理模型按季度拆解交付目标、运行指标和治理动作，形成完整的年度执行与复盘机制。",
                "images": ["annual-model.png"],
            },
        },
        "okr": {
            "product_chain": "数字化研发与审批产品链",
            "objective": "建设统一立项审批平台，提升审批效率并降低人工漏审风险。",
            "squad_okr": "审批治理战队负责规则落地与流程优化。",
            "related_products": ["立项工作台", "审批中心"],
            "time_range": {"start": "2026-04", "end": "2028-12"},
            "key_results": ["审批平均时长缩短 80%", "规则覆盖率达到 100%", "审批过程全链路可追溯"],
        },
        "scope": {
            "business_processes": ["立项申请", "信息采集", "规则校验", "审批结果输出"],
            "content_list": ["审批引擎", "规则管理", "结果追溯", "配置前端"],
            "microservices": ["approval-core", "rule-engine", "trace-center"],
            "microapps": ["approval-console", "rule-config"],
        },
        "architecture_reviews": {
            "business": "业务架构覆盖审批角色、流程泳道、输入输出和例外处理。",
            "data": "数据架构明确本体模型、源系统映射、结果留痕和报表输出。",
            "technology": "技术架构采用接口适配层、规则引擎层和 FastAPI 服务层。",
            "security": "安全架构明确访问控制、审计日志、Token 管理和敏感信息保护。",
        },
        "tam_models": {
            "capability": [
                {
                    "title": "审批自动化能力",
                    "current_state": "当前以人工审核为主",
                    "benefit_department": "数字化管理部",
                    "target_3y": "三年内形成标准化审批中台能力",
                    "calculation_basis": "按审批人时和立项量测算",
                }
            ],
            "result": [
                {
                    "title": "审批效率收益",
                    "current_state": "平均审批耗时较长",
                    "benefit_department": "各立项审批部门",
                    "target_3y": "审批时长持续下降并稳定控制",
                    "calculation_basis": "基于年度立项数量和处理时长估算",
                }
            ],
            "management": [
                {
                    "title": "治理体系成熟度",
                    "current_state": "规则维护分散",
                    "benefit_department": "流程治理团队",
                    "target_3y": "形成统一规则配置治理体系",
                    "calculation_basis": "按规则变更效率和审计要求测算",
                }
            ],
        },
        "project_value": "项目价值体现在统一规则、提升审批效率、降低风险并形成标准化数据资产。",
        "milestones": {
            "approval_plan": {"start": "2026-04-01", "end": "2026-05-15"},
            "contract_plan": {"start": "2026-05-16", "end": "2026-06-30"},
            "target_plan": {"start": "2026-07-01", "end": "2026-12-31"},
        },
        "organization": {
            "development_mode": "自有三方混编" if category in CORE_CATEGORIES else "",
            "members": [
                {"name": "张三", "role": "PO", "level": "P7", "task_plan": "负责需求与验收", "workload": "30%"},
                {"name": "李四", "role": "架构师", "level": "P8", "task_plan": "负责总体架构与规则设计", "workload": "25%"},
                {"name": "王五", "role": "开发", "level": "P6", "task_plan": "负责服务端和前端实现", "workload": "45%"},
            ],
        },
        "budget": {
            "cost_items": [
                {
                    "name": "平台开发实施",
                    "amount": 1200000,
                    "budget_subject": "研发服务费",
                    "calculation": "按人月与实施工作包测算",
                    "unit_price_standard": "2 万/人月",
                    "yearly_split": ["2026:700000", "2027:500000"],
                    "purchase_mode": "询比采购",
                    "supplier_basis": "供应商评价表与交流纪要",
                }
            ]
        },
        "cost_change": {
            "fixed_project": False,
            "history_analysis": "",
            "reason": "本年度为新建项目，无历史费用波动。",
        },
    }


def normalize_generated_bundle(bundle: dict[str, Any], category: str) -> dict[str, Any]:
    project_definition = bundle.get("project_definition", {})
    return {
        "project_name": project_definition.get("name", "未命名项目"),
        "category": category,
        "project_content": {
            "background": {
                "title": "项目背景",
                "content": project_definition.get("background", ""),
                "images": [],
            },
            "target": {
                "title": "项目目标",
                "content": "\n".join(project_definition.get("goals", [])),
                "images": [],
            },
            "solution": {
                "title": "项目方案",
                "content": project_definition.get("technical_solution", ""),
                "images": [],
            },
            "panorama": {
                "title": "",
                "content": "",
                "images": [],
            },
            "annual_model": {
                "title": "",
                "content": "",
                "images": [],
            },
        },
        "okr": {
            "product_chain": "",
            "objective": project_definition.get("overview", ""),
            "squad_okr": "",
            "related_products": [],
            "time_range": {},
            "key_results": project_definition.get("goals", []),
        },
        "scope": {
            "business_processes": project_definition.get("scope_included", []),
            "content_list": project_definition.get("scope_excluded", []),
            "microservices": [],
            "microapps": [],
        },
        "architecture_reviews": {
            "business": project_definition.get("architecture", ""),
            "data": "",
            "technology": "",
            "security": "",
        },
        "tam_models": {"capability": [], "result": [], "management": []},
        "project_value": project_definition.get("project_value", ""),
        "milestones": {"approval_plan": {}, "contract_plan": {}, "target_plan": {}},
        "organization": {"development_mode": "", "members": []},
        "budget": {"cost_items": []},
        "cost_change": {"fixed_project": False, "history_analysis": "", "reason": ""},
    }


def evaluate_approval(document: dict[str, Any], category: str | None = None) -> dict[str, Any]:
    active_category = category or document.get("category") or "工作台开发及实施"
    rules_bundle = load_rules_bundle()
    active_rules = select_active_rules(rules_bundle, active_category)
    results = [evaluate_rule(rule, document, active_category) for rule in active_rules]
    summary = summarize_results(active_category, results)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_name": document.get("project_name", "未命名项目"),
        "category": active_category,
        "decision": summary["decision"],
        "score": summary["score"],
        "statistics": summary["statistics"],
        "findings": summary["findings"],
        "rule_results": results,
    }
    write_json(GENERATED_DIR / "latest_approval_result.json", report)
    return report


def load_or_create_sample_document() -> dict[str, Any]:
    sample_path = SAMPLE_INPUT_PATH
    if sample_path.exists():
        return json.loads(sample_path.read_text(encoding="utf-8"))
    sample = build_sample_approval_document()
    write_json(sample_path, sample)
    return sample
