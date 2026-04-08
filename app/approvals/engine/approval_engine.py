"""Split support helpers out of the main module for readability."""

from __future__ import annotations

from .approval_engine_support import *  # noqa: F401,F403

def evaluate_rule(rule: dict[str, Any], document: dict[str, Any], category: str, scene: str = "initiation") -> dict[str, Any]:
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
    acceptance = get_value(document, "acceptance") or {}
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
        panorama_section = content_sections.get("panorama") or {}
        if normalize_scene(scene) == "acceptance" and section_marked_not_involved(panorama_section):
            passed = True
            message = "业务全景图标记为不涉及，按验收规则视为通过"
            evidence = normalize_text(panorama_section)
        elif (
            normalize_scene(scene) == "acceptance"
            and normalize_lookup_key(review_content) == normalize_lookup_key("业务全景图内容")
            and is_present((panorama_section or {}).get("content"))
        ):
            passed = True
            message = "业务全景图已提供内容，按验收场景通过"
            evidence = normalize_text(panorama_section)
        elif system_development_project:
            passed = True
            message = "系统开发项目不要求业务全景图"
            evidence = "exempt_for_system_development_project"
        else:
            passed, message = evaluate_title_content_image(panorama_section, review_content)
            evidence = normalize_text(panorama_section)
    elif review_point == "年度管理模型":
        normalized_review_content = normalize_lookup_key(review_content)
        if normalize_scene(scene) == "acceptance" and normalized_review_content == normalize_lookup_key("业务流程"):
            value = scope.get("business_processes") or scope.get("content_list")
            passed = is_present(value)
            message = "业务流程材料完整" if passed else "缺少业务流程"
            evidence = normalize_text(value)
        elif normalize_scene(scene) == "acceptance" and normalized_review_content == normalize_lookup_key("系统"):
            value = first_present(scope.get("microservices"), scope.get("microapps"))
            passed = is_present(value) or section_marked_not_involved(value)
            message = "系统信息已标记不涉及，按验收规则通过" if section_marked_not_involved(value) else "系统材料完整" if passed else "缺少系统"
            evidence = normalize_text(value)
        elif system_development_project:
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
        value = architecture.get(field_map.get(review_content, ""))
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
        value = milestones.get(field_map.get(review_content, ""))
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
    elif review_point == "验收方案评审":
        section = content_sections.get("acceptance_plan") or {}
        if not any(is_present(section.get(key)) for key in ["title", "content", "images"]):
            passed = True
            message = "当前未配置验收方案材料，按无需评审处理。"
            evidence = ""
        else:
            passed, message = evaluate_title_content_image(section, review_content)
            evidence = normalize_text(section)
    elif normalize_lookup_key(review_point) in {normalize_lookup_key("任务单"), normalize_lookup_key("合同")}:
        passed, message, evidence = evaluate_acceptance_pair_rule(rule, acceptance, review_point, review_content)
    elif review_point == "任务单":
        value = acceptance.get("task_list") if "清单" in str(review_content or "") else acceptance.get("task_acceptance_list")
        passed = is_present(value)
        message = "任务单材料完整" if passed else f"缺少{review_content}"
        evidence = normalize_text(value)
    elif review_point == "合同":
        value = acceptance.get("contract_list") if "清单" in str(review_content or "") else acceptance.get("contract_acceptance_list")
        passed = is_present(value)
        message = "合同材料完整" if passed else f"缺少{review_content}"
        evidence = normalize_text(value)
    elif review_point == "交付物":
        value = acceptance.get("deliverables")
        passed = is_present(value)
        message = "交付物材料完整" if passed else "缺少交付物清单"
        evidence = normalize_text(value)
    elif review_point in {"长尾费用", "历史投入"}:
        passed = True
        message = "当前规则标记为不需要。"
        evidence = ""
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


def evaluate_task_order_rule(rule: dict[str, Any], context: dict[str, Any], category: str) -> dict[str, Any]:
    review_point = canonical_review_point(rule["review_point"])
    review_content = str(rule.get("review_content") or "").strip()
    severity = "major" if "非必填" in review_content or "审批节点" in review_point else "critical"
    lookup_point = normalize_lookup_key(review_point)
    lookup_content = normalize_lookup_key(review_content)
    passed = False
    message = ""
    evidence = ""

    basic_info = context.get("basic_info") or {}
    business_architecture = context.get("business_architecture") or {}
    task_assignment = context.get("task_assignment") or {}
    staffing = context.get("staffing") or {}
    cost_estimation = context.get("cost_estimation") or {}
    technical_requirements = context.get("technical_requirements") or {}

    if lookup_point == normalize_lookup_key("基本信息"):
        value = basic_info.get(review_content)
        passed = is_present(value)
        message = "任务单基本信息已补充" if passed else f"缺少{review_content}"
        evidence = normalize_text(value)
    elif lookup_point == normalize_lookup_key("关联目标"):
        value = basic_info.get("项目目标")
        passed = len(normalize_list_like(value)) > 0 or is_present(value)
        message = "已关联项目目标" if passed else "缺少项目目标"
        evidence = normalize_text(value)
    elif lookup_point == normalize_lookup_key("关联的产品"):
        value = basic_info.get("产品名称")
        passed = len(normalize_list_like(value)) > 0 or is_present(value)
        message = "已关联产品" if passed else "缺少关联产品"
        evidence = normalize_text(value)
    elif lookup_point == normalize_lookup_key("采购说明及原因"):
        field_name = "选择供应商原因" if "供应商" in review_content else "采购说明"
        value = basic_info.get(field_name)
        passed = is_present(value)
        message = "采购说明已补充" if passed else f"缺少{review_content}"
        evidence = normalize_text(value)
    elif lookup_point == normalize_lookup_key("业务单元清单"):
        rows = normalize_list_like(business_architecture.get("业务单元清单"))
        if lookup_content == normalize_lookup_key("业务对象数字化"):
            passed = any(is_present(item.get("business_object")) for item in rows if isinstance(item, dict))
        elif lookup_content == normalize_lookup_key("业务规则数字化"):
            passed = any(is_present(item.get("business_unit")) for item in rows if isinstance(item, dict))
        else:
            passed = any(is_present(item.get("business_process")) for item in rows if isinstance(item, dict))
        message = "业务单元清单已补充" if passed else f"缺少{review_content}"
        evidence = normalize_text(rows)
    elif lookup_point == normalize_lookup_key("审批节点"):
        rows = normalize_list_like(business_architecture.get("审批节点"))
        passed = any(is_present(item.get("description")) or normalize_number(item.get("removed_nodes")) > 0 for item in rows if isinstance(item, dict))
        message = "审批节点说明已补充" if passed else f"缺少{review_content}"
        evidence = normalize_text(rows)
    elif lookup_point == normalize_lookup_key("业务流程清单"):
        value = task_assignment.get(review_content)
        if "非必填" in review_content:
            passed = True
            message = "指标列表可为空"
        else:
            passed = len(normalize_list_like(value)) > 0 or is_present(value)
            message = "任务填写已补充" if passed else f"缺少{review_content}"
        evidence = normalize_text(value)
    elif lookup_point == normalize_lookup_key("人员配置及费用"):
        if "预计费用" in review_content:
            value = staffing.get("预计费用")
            passed = normalize_number(value) > 0
        else:
            rows = normalize_list_like(staffing.get("岗位、职级、预计人天、人员单价、预计费用"))
            passed = bool(rows) and all(
                is_present(item.get("post_name"))
                and is_present(item.get("level_name"))
                and normalize_number(item.get("expected_days")) > 0
                and normalize_number(item.get("unit_price")) > 0
                and normalize_number(item.get("estimated_cost")) > 0
                for item in rows
                if isinstance(item, dict)
            )
            value = rows
        message = "人员配置与费用已补充" if passed else f"缺少{review_content}"
        evidence = normalize_text(value)
    elif lookup_point == normalize_lookup_key("本次任务单费用"):
        rows = normalize_list_like(cost_estimation.get("岗位、职级、人天、单价、费用"))
        passed = bool(rows) and all(
            is_present(item.get("post_name"))
            and is_present(item.get("level_name"))
            and normalize_number(item.get("expected_days")) > 0
            and normalize_number(item.get("unit_price")) > 0
            and normalize_number(item.get("estimated_cost")) > 0
            for item in rows
            if isinstance(item, dict)
        )
        message = "本次任务单费用已补充" if passed else "缺少本次任务单费用明细"
        evidence = normalize_text(rows)
    elif lookup_point == normalize_lookup_key("历史任务单费用"):
        value = cost_estimation.get("历史任务单明细")
        passed = len(normalize_list_like(value)) > 0 or normalize_number(cost_estimation.get("历史任务单费用")) > 0
        message = "历史任务单费用已补充" if passed else "缺少历史任务单费用明细"
        evidence = normalize_text(value)
    elif lookup_point == normalize_lookup_key("技术要求"):
        value = technical_requirements.get(review_content)
        passed = is_present(value)
        message = "技术要求已补充" if passed else f"缺少{review_content}"
        evidence = normalize_text(value)
    else:
        message = f"未识别的任务单规则: {review_point}/{review_content}"

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


def evaluate_approval(document: dict[str, Any], category: str | None = None, scene: str = "initiation") -> dict[str, Any]:
    normalized_scene = normalize_scene(scene)
    active_category = category or document.get("category") or "工作台开发及实施"
    rules_bundle = load_rules_bundle(scene=normalized_scene)
    active_rules = select_active_rules(rules_bundle, active_category)
    if normalized_scene == "task_order":
        task_order_context = build_task_order_review_context(document)
        results = [evaluate_task_order_rule(rule, task_order_context, active_category) for rule in active_rules]
    else:
        results = [evaluate_rule(rule, document, active_category, normalized_scene) for rule in active_rules]
    summary = summarize_results(active_category, results)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scene": normalized_scene,
        "project_name": document.get("project_name", "未命名项目"),
        "category": active_category,
        "decision": summary["decision"],
        "score": summary["score"],
        "statistics": summary["statistics"],
        "findings": summary["findings"],
        "rule_results": results,
    }
    latest_result_path = scene_latest_approval_result_path(normalized_scene)
    write_json(latest_result_path, report)
    if normalized_scene == "initiation" and latest_result_path != LEGACY_LATEST_APPROVAL_RESULT_PATH:
        write_json(LEGACY_LATEST_APPROVAL_RESULT_PATH, report)
    return report

def load_or_create_sample_document() -> dict[str, Any]:
    sample_path = SAMPLE_INPUT_PATH
    if sample_path.exists():
        return json.loads(sample_path.read_text(encoding="utf-8"))
    sample = build_sample_approval_document()
    write_json(sample_path, sample)
    return sample
