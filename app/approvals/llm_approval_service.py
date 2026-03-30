"""LLM-driven approval workflow with segmented prompts and persisted artifacts."""

from __future__ import annotations

import json
import os
import re
import shutil
from concurrent import futures
from datetime import datetime
from pathlib import Path
from typing import Any

from app.approvals.approval_engine import evaluate_approval
from app.core.llm_client import chat_json
from app.core.paths import scene_approval_runs_dir, scene_skills_dir

DEFAULT_OUTPUT_SCHEMA = {
    "decision": "通过 | 需补充材料 | 驳回 | 需更多信息",
    "summary": "结论摘要",
    "item_results": [
        {
            "rule_id": "规则ID",
            "status": "pass | fail | needs_more_info",
            "reason": "判断原因",
            "evidence": ["引用的字段或事实"],
            "suggestion": "补充建议",
        }
    ],
    "risks": ["关键风险"],
    "missing_information": ["缺失信息"],
}

TAB_DOCUMENT_KEYS = {
    "项目内容": ["project_summary", "project_content", "okr", "scope"],
    "专业领域评审": ["project_summary", "architecture_reviews", "scope"],
    "TAM模型评审": ["project_summary", "tam_models"],
    "项目价值": ["project_summary", "project_value"],
    "项目里程碑": ["project_summary", "milestones"],
    "组织架构": ["project_summary", "organization"],
    "预算信息": ["project_summary", "budget"],
    "费用变化点": ["project_summary", "cost_change"],
}

TAB_ENDPOINT_KEYS = {
    "项目内容": [
        "project_base_info",
        "project_uploading",
        "project_goal",
        "project_scope_dev",
        "project_scope_ops",
        "project_scope_ops_get_scope",
        "project_scope_ops_legacy",
        "system_scope_okr",
        "system_scope",
    ],
    "专业领域评审": ["project_scope_dev"],
    "TAM模型评审": ["tam_info"],
    "项目价值": ["project_value"],
    "项目里程碑": ["milestones"],
    "组织架构": ["organization", "organization_framework", "organization_flag_0", "organization_flag_1"],
    "预算信息": ["budget", "project_base_info"],
    "费用变化点": ["cost_change", "project_base_info"],
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:120] or "run"


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def normalize_rule_status(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in {"pass", "fail", "needs_more_info"}:
        return normalized
    return "needs_more_info" if normalized else ""


def to_evidence_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if value is None:
        return []
    return [str(value).strip()]


def compact_for_prompt(
    value: Any,
    *,
    max_depth: int = 5,
    max_dict_items: int = 18,
    max_list_items: int = 12,
    max_string_length: int = 1600,
    depth: int = 0,
) -> Any:
    if depth >= max_depth:
        if isinstance(value, dict):
            return {"_truncated": "dict"}
        if isinstance(value, list):
            return [{"_truncated": "list"}]
        return str(value)[:max_string_length]

    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) <= max_string_length:
            return text
        return f"{text[:max_string_length]} ...[truncated {len(text) - max_string_length} chars]"
    if isinstance(value, list):
        items = [
            compact_for_prompt(
                item,
                max_depth=max_depth,
                max_dict_items=max_dict_items,
                max_list_items=max_list_items,
                max_string_length=max_string_length,
                depth=depth + 1,
            )
            for item in value[:max_list_items]
        ]
        if len(value) > max_list_items:
            items.append({"_truncated_items": len(value) - max_list_items})
        return items
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_dict_items:
                compacted["_truncated_keys"] = len(value) - max_dict_items
                break
            compacted[str(key)] = compact_for_prompt(
                item,
                max_depth=max_depth,
                max_dict_items=max_dict_items,
                max_list_items=max_list_items,
                max_string_length=max_string_length,
                depth=depth + 1,
            )
        return compacted
    return str(value)


def normalize_scene(scene: str | None) -> str:
    normalized = str(scene or "").strip().lower()
    if normalized in {"task_order", "task-order", "taskorder"}:
        return "task_order"
    return "acceptance" if normalized == "acceptance" else "initiation"


def scene_skill_dir(scene: str) -> Path:
    return scene_skills_dir(scene)


def load_item_skill_manifest(category: str | None = None, scene: str = "initiation") -> list[dict[str, Any]]:
    manifest_path = scene_skill_dir(scene) / "manifest.json"
    if not manifest_path.exists():
        return []
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    skills = payload.get("skills", [])
    if not category:
        return skills
    filtered = [skill for skill in skills if not skill.get("categories") or category in skill.get("categories", [])]
    return filtered or skills


def llm_segment_workers() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_LLM_SEGMENT_WORKERS", "3") or "3").strip()
    try:
        workers = int(raw_value)
    except ValueError:
        workers = 3
    return max(1, min(workers, 8))


def build_document_excerpt(document: dict[str, Any], tab_name: str) -> dict[str, Any]:
    excerpt = {
        "project_name": document.get("project_name"),
        "project_id": document.get("project_id"),
    }
    for key in TAB_DOCUMENT_KEYS.get(tab_name, ["project_summary"]):
        excerpt[key] = document.get(key)
    return compact_for_prompt(excerpt)


def build_snapshot_excerpt(snapshot: dict[str, Any], tab_name: str) -> dict[str, Any]:
    endpoints = snapshot.get("endpoints") or {}
    excerpt: dict[str, Any] = {"project_id": snapshot.get("project_id"), "endpoints": {}}
    for name in TAB_ENDPOINT_KEYS.get(tab_name, []):
        endpoint = endpoints.get(name) or {}
        excerpt["endpoints"][name] = {
            "ok": endpoint.get("ok"),
            "code": endpoint.get("code"),
            "message": endpoint.get("message"),
            "data_preview": compact_for_prompt(endpoint.get("data")),
        }
    return excerpt


def build_skill_baseline(skill: dict[str, Any], deterministic_result: dict[str, Any]) -> dict[str, Any]:
    rule_ids = set(skill.get("rule_ids") or [])
    results = deterministic_result.get("rule_results") or []
    related_results = [item for item in results if str(item.get("rule_id") or "") in rule_ids]
    findings = [item for item in related_results if item.get("status") == "fail"]
    return {
        "decision": deterministic_result.get("decision"),
        "score": deterministic_result.get("score"),
        "statistics": {
            "total_rules": len(related_results),
            "failed_rules": len(findings),
            "critical_failures": len([item for item in findings if item.get("severity") == "critical"]),
            "major_failures": len([item for item in findings if item.get("severity") == "major"]),
            "minor_failures": len([item for item in findings if item.get("severity") == "minor"]),
        },
        "rule_results": compact_for_prompt(related_results, max_list_items=20, max_string_length=800),
    }


def compact_skill(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "skill_name": skill.get("skill_name", ""),
        "review_point": skill.get("review_point", ""),
        "tab": skill.get("tab", ""),
        "rule_count": skill.get("rule_count", 0),
        "review_points": skill.get("review_points", []),
        "review_contents": skill.get("review_contents", []),
        "rule_ids": skill.get("rule_ids", []),
        "summary": skill.get("summary", ""),
    }


def build_authoritative_summary(deterministic_result: dict[str, Any]) -> str:
    findings = deterministic_result.get("findings") or []
    decision = str(deterministic_result.get("decision") or "").strip() or "需要更多信息"
    statistics = deterministic_result.get("statistics") or {}
    total_rules = statistics.get("total_rules") or 0
    passed_rules = statistics.get("passed_rules") or 0
    if not findings:
        return f"规则引擎基线结果为{decision}。{passed_rules}/{total_rules}条规则通过，当前未发现阻断性缺陷。"
    finding_text = "；".join(
        f"{item.get('rule_id')}: {item.get('message')}"
        for item in findings[:5]
        if str(item.get("rule_id") or "").strip() and str(item.get("message") or "").strip()
    )
    return f"规则引擎基线结果为{decision}。{len(findings)}条规则未通过，主要问题：{finding_text}。"


def build_authoritative_item_results(
    deterministic_result: dict[str, Any],
    segment_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    authoritative_items: list[dict[str, Any]] = []
    for rule in deterministic_result.get("rule_results") or []:
        authoritative_items.append(
            {
                "rule_id": str(rule.get("rule_id") or "").strip(),
                "status": normalize_rule_status(rule.get("status")) or "fail",
                "reason": str(rule.get("message") or "").strip(),
                "evidence": to_evidence_list(rule.get("evidence")),
                "suggestion": str(rule.get("suggestion") or "").strip(),
            }
        )
    return authoritative_items


def build_authoritative_risks(deterministic_result: dict[str, Any]) -> list[str]:
    findings = deterministic_result.get("findings") or []
    return dedupe_strings(
        [
            str(item.get("message") or "").strip()
            for item in findings
            if str(item.get("message") or "").strip()
        ]
    )


def build_authoritative_missing_information(deterministic_result: dict[str, Any]) -> list[str]:
    findings = deterministic_result.get("findings") or []
    values: list[str] = []
    for item in findings:
        review_content = str(item.get("review_content") or "").strip()
        suggestion = str(item.get("suggestion") or "").strip()
        if review_content:
            values.append(review_content)
        if suggestion:
            values.append(suggestion)
    return dedupe_strings(values)


def build_positive_summary(deterministic_result: dict[str, Any]) -> str:
    statistics = deterministic_result.get("statistics") or {}
    passed_rules = int(statistics.get("passed_rules") or 0)
    total_rules = int(statistics.get("total_rules") or 0)
    return (
        f"当前审批项已全部通过，{passed_rules}/{total_rules}条规则校验通过，"
        "未发现需补充材料或驳回项，可进入后续立项审批与实施推进。"
    )


def build_finding_summary(deterministic_result: dict[str, Any]) -> str:
    findings = deterministic_result.get("findings") or []
    decision = str(deterministic_result.get("decision") or "").strip() or "需更多信息"
    finding_text = "；".join(
        f"{item.get('rule_id')}: {item.get('message')}"
        for item in findings[:5]
        if str(item.get("rule_id") or "").strip() and str(item.get("message") or "").strip()
    )
    return f"规则引擎基线结果为{decision}。{len(findings)}条规则未通过，主要问题：{finding_text}。"


def build_authoritative_summary_v2(deterministic_result: dict[str, Any]) -> str:
    findings = deterministic_result.get("findings") or []
    if not findings:
        return build_positive_summary(deterministic_result)
    return build_finding_summary(deterministic_result)


def build_authoritative_positive_evidence(deterministic_result: dict[str, Any]) -> list[str]:
    statistics = deterministic_result.get("statistics") or {}
    findings = deterministic_result.get("findings") or []
    decision = str(deterministic_result.get("decision") or "").strip()
    passed_rules = int(statistics.get("passed_rules") or 0)
    total_rules = int(statistics.get("total_rules") or 0)
    passed_points = dedupe_strings(
        [
            str(item.get("review_point") or "").strip()
            for item in (deterministic_result.get("rule_results") or [])
            if str(item.get("status") or "").strip() == "pass" and str(item.get("review_point") or "").strip()
        ]
    )

    if decision != "通过" or findings:
        return []

    evidence: list[str] = []
    if total_rules:
        evidence.append(f"共通过 {passed_rules}/{total_rules} 条审批规则校验。")
    evidence.append("当前审批基线未发现需补充材料或驳回项。")
    if passed_points:
        label = "、".join(passed_points[:6])
        if len(passed_points) > 6:
            label = f"{label} 等"
        evidence.append(f"已覆盖并通过的审批项包括：{label}。")
    return evidence[:3]


def normalize_commentary_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\b(?:id|projectid|project_id)\s*[:：]\s*[\w-]+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,.;:，。；：")


def clip_commentary_text(value: Any, max_length: int = 28) -> str:
    text = normalize_commentary_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip('，。；、 ')}..."


def extract_content_section_text(document: dict[str, Any], section_key: str) -> str:
    section = (document.get("project_content") or {}).get(section_key) or {}
    if not isinstance(section, dict):
        return ""
    return normalize_commentary_text("，".join([section.get("title") or "", section.get("content") or ""]))


def has_meaningful_text(value: Any, min_length: int = 8) -> bool:
    return len(normalize_commentary_text(value)) >= min_length


def summarize_core_materials(document: dict[str, Any]) -> str:
    sections = []
    if has_meaningful_text(extract_content_section_text(document, "background")):
        sections.append("项目背景")
    if has_meaningful_text((document.get("okr") or {}).get("objective") or extract_content_section_text(document, "target")):
        sections.append("项目目标")
    if has_meaningful_text(extract_content_section_text(document, "solution")):
        sections.append("实施方案")
    if has_meaningful_text(document.get("project_value")):
        sections.append("项目价值")
    if len(sections) >= 4:
        return "项目背景、目标、实施方案与价值说明较为完整"
    if len(sections) == 3:
        return f"{'、'.join(sections)}已形成较完整的申报表达"
    if len(sections) == 2:
        return f"{'、'.join(sections)}已有较明确描述"
    return ""


def build_commentary_context_text(document: dict[str, Any], project_name: str) -> str:
    parts = [
        project_name,
        document.get("category"),
        extract_content_section_text(document, "background"),
        (document.get("okr") or {}).get("objective"),
        extract_content_section_text(document, "solution"),
        document.get("project_value"),
    ]
    return normalize_commentary_text(" ".join([str(part or "") for part in parts]))


def contains_any_keyword(text: str, keywords: list[str]) -> bool:
    normalized = normalize_commentary_text(text).lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def summarize_project_highlights(document: dict[str, Any], project_name: str) -> str:
    context_text = build_commentary_context_text(document, project_name)
    category_text = normalize_commentary_text(document.get("category"))
    highlights: list[str] = []

    if contains_any_keyword(context_text, ["智能体", "openmind", "大模型", "ai", "人工智能", "模型"]):
        highlights.append("项目聚焦企业级智能体与大模型能力建设，方向上具有较强前瞻性，符合当前企业智能化升级趋势")
    if contains_any_keyword(context_text, ["汽车", "整车", "一汽", "主机厂"]):
        highlights.append("方案与汽车行业数字化、智能化转型需求结合较紧，有助于形成贴合行业场景的能力底座")
    if contains_any_keyword(context_text, ["平台", "中台", "底座", "工作台", "openmind"]):
        highlights.append("项目强调平台化沉淀与能力复用，既关注本期建设成效，也兼顾后续多场景推广价值")
    if contains_any_keyword(context_text, ["知识", "数据", "语料", "治理", "资产"]):
        highlights.append("在数据与知识资产沉淀方面具备延展空间，有利于持续增强模型应用效果和组织复用效率")
    if contains_any_keyword(context_text, ["流程", "协同", "运营", "审批", "管理", "效率"]):
        highlights.append("项目兼顾业务协同与运营提效，预期能够对管理效率提升和流程标准化形成直接支撑")
    if "系统建设及运营" in category_text and not highlights:
        highlights.append("项目兼顾系统建设与运营延展，整体思路较符合企业级平台持续演进的建设规律")

    return "；".join(highlights[:3])


def summarize_architecture_reviews(document: dict[str, Any]) -> str:
    architecture_reviews = document.get("architecture_reviews") or {}
    labels = []
    field_map = {
        "business": "业务架构",
        "data": "数据架构",
        "technology": "技术架构",
        "security": "安全架构",
    }
    for key, label in field_map.items():
        value = architecture_reviews.get(key)
        if normalize_commentary_text(value):
            labels.append(label)
    if len(labels) >= 3:
        return f"已覆盖{'、'.join(labels[:4])}等关键评审维度"
    if labels:
        return f"已补充{'、'.join(labels[:4])}评审内容"
    return ""


def summarize_tam_models(document: dict[str, Any]) -> str:
    tam_models = document.get("tam_models") or {}
    labels = []
    field_map = {
        "capability": "能力模型",
        "result": "结果模型",
        "management": "管理体系模型",
    }
    for key, label in field_map.items():
        if tam_models.get(key):
            labels.append(label)
    if len(labels) >= 2:
        return f"TAM模型已覆盖{'、'.join(labels)}"
    if labels:
        return f"已补充{labels[0]}"
    return ""


def summarize_milestones(document: dict[str, Any]) -> str:
    milestones = document.get("milestones") or {}
    labels = []
    field_map = {
        "approval_plan": "立项计划",
        "contract_plan": "合同计划",
        "target_plan": "目标计划",
    }
    for key, label in field_map.items():
        item = milestones.get(key) or {}
        if (item.get("start") or item.get("end")):
            labels.append(label)
    if len(labels) >= 2:
        return f"里程碑计划覆盖{'、'.join(labels)}"
    if labels:
        return f"已明确{labels[0]}"
    return ""


def summarize_organization(document: dict[str, Any]) -> str:
    organization = document.get("organization") or {}
    members = organization.get("members") or []
    development_mode = normalize_commentary_text(organization.get("development_mode"))
    details = []
    if development_mode:
        details.append("组织分工与实施方式已有安排")
    if members:
        details.append(f"已补充{len(members)}名关键成员信息")
    return "，".join(details)


def summarize_budget(document: dict[str, Any]) -> str:
    budget_items = (document.get("budget") or {}).get("cost_items") or []
    if not budget_items:
        return ""
    subjects = []
    for item in budget_items[:3]:
        label = normalize_commentary_text(item.get("budget_subject") or item.get("name"))
        if label:
            subjects.append(label)
    subject_text = "、".join(subjects[:3])
    if subject_text and len(budget_items) >= 2:
        return f"预算测算已细化到费用构成层面，涵盖{subject_text}等内容"
    return f"预算中已列出{len(budget_items)}项费用构成"


def build_pass_project_commentary(document: dict[str, Any], deterministic_result: dict[str, Any]) -> str:
    findings = deterministic_result.get("findings") or []
    decision = str(deterministic_result.get("decision") or "").strip()
    if decision != "通过" or findings:
        return ""

    summary = document.get("project_summary") or {}
    project_name = normalize_commentary_text(summary.get("project_name") or document.get("project_name") or "该项目")
    core_materials = summarize_core_materials(document)
    project_highlights = summarize_project_highlights(document, project_name)
    architecture = summarize_architecture_reviews(document)
    tam_models = summarize_tam_models(document)
    milestones = summarize_milestones(document)
    organization = summarize_organization(document)
    budget = summarize_budget(document)
    statistics = deterministic_result.get("statistics") or {}
    passed_rules = int(statistics.get("passed_rules") or 0)
    total_rules = int(statistics.get("total_rules") or 0)

    sentences = [
        f"{project_name}的申报内容整体较扎实，项目定位、建设思路与实施安排之间衔接顺畅，体现出较好的立项成熟度。"
    ]
    if project_highlights:
        sentences.append(f"从项目本身看，{project_highlights}。")
    if core_materials:
        sentences.append(f"从当前填报情况看，{core_materials}，能够较好支撑项目价值论证、建设范围界定和后续实施推进。")
    else:
        sentences.append("从当前填报情况看，项目核心申报信息较为聚焦，能够支撑本次建设诉求说明和后续方案展开。")
    if architecture or tam_models:
        detail = "，".join([item for item in [architecture, tam_models] if item])
        sentences.append(f"在专业评审与能力模型方面，{detail}，说明团队已对关键设计要素、建设路径和预期成效形成较清晰判断。")
    if milestones or organization or budget:
        detail = "，".join([item for item in [milestones, organization, budget] if item])
        sentences.append(f"同时，{detail}，进一步增强了项目在实施节奏、资源协同和投入规划上的可执行性，也为后续落地见效提供了保障。")
    else:
        sentences.append("同时，项目在推进节奏和实施保障方面具备较明确的安排，具备继续落地实施的基础。")
    if total_rules:
        sentences.append(f"结合本次评审结果，{passed_rules}/{total_rules}条规则校验通过，说明申报材料在完整性、一致性和可追溯性方面达到了较好水平。")
    sentences.append("整体来看，该项目不仅具备继续推进审批与实施的条件，也有望形成较好的业务带动作用和示范推广价值。")

    commentary = "".join(sentences)
    if len(commentary) < 200:
        commentary += "从当前资料质量看，项目团队对建设内容、预期收益和执行条件已有较充分准备，后续推进风险总体可控。"
    if len(commentary) > 300:
        commentary = f"{commentary[:299].rstrip('，。；、 ')}。"
    return commentary


def build_segment_messages(
    *,
    project_name: str,
    category: str,
    skill: dict[str, Any],
    document: dict[str, Any],
    snapshot: dict[str, Any],
    deterministic_result: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    tab_name = str(skill.get("tab") or skill.get("review_point") or "未命名分段")
    payload = {
        "task": "请只针对当前审批页面分段做判断，不要评审无关页面内容。",
        "project_name": project_name,
        "category": category,
        "review_tab": tab_name,
        "required_output_schema": DEFAULT_OUTPUT_SCHEMA,
        "approval_item_skill": compact_skill(skill),
        "project_page_document": build_document_excerpt(document, tab_name),
        "project_snapshot_excerpt": build_snapshot_excerpt(snapshot, tab_name),
        "rule_engine_baseline": build_skill_baseline(skill, deterministic_result),
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是企业项目立项审批专家。"
                "现在只评审一个页面分段，必须基于提供的页面正文、相关接口摘要和规则基线输出严格 JSON。"
                "不得把规则基线中已通过的规则再写成 fail 或 needs_more_info。"
                "如果信息不足，明确写 needs_more_info 和缺失字段。"
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    return messages, payload


def build_summary_messages(
    *,
    project_name: str,
    category: str,
    deterministic_result: dict[str, Any],
    segment_results: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    payload = {
        "task": "请根据各页面分段审批结果汇总出项目总评，不要重新编造事实。",
        "project_name": project_name,
        "category": category,
        "required_output_schema": DEFAULT_OUTPUT_SCHEMA,
        "rule_engine_baseline_summary": {
            "decision": deterministic_result.get("decision"),
            "score": deterministic_result.get("score"),
            "statistics": deterministic_result.get("statistics"),
            "findings": compact_for_prompt(deterministic_result.get("findings") or [], max_list_items=20, max_string_length=800),
        },
        "segment_results": compact_for_prompt(segment_results, max_list_items=20, max_string_length=1200),
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是企业项目立项审批专家。"
                "请基于各页面审批结果做总体结论汇总，输出严格 JSON。"
                "总体结论必须与分段结论和基线失败项保持一致。"
                "规则基线中已通过的规则，不得在总评中改写为缺失或不通过。"
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    return messages, payload


def aggregate_segment_results(segment_results: list[dict[str, Any]]) -> dict[str, Any]:
    item_results: list[dict[str, Any]] = []
    risks: list[str] = []
    missing_information: list[str] = []
    decisions: list[str] = []
    summaries: list[str] = []

    for segment in segment_results:
        result = segment.get("result") or {}
        tab_name = segment.get("tab")
        decision = str(result.get("decision") or "").strip()
        summary = str(result.get("summary") or "").strip()
        if decision:
            decisions.append(decision)
        if summary:
            summaries.append(f"{tab_name}: {summary}")
        for item in result.get("item_results") or []:
            normalized = dict(item)
            normalized.setdefault("tab", tab_name)
            item_results.append(normalized)
        risks.extend([str(item) for item in (result.get("risks") or []) if str(item).strip()])
        missing_information.extend([str(item) for item in (result.get("missing_information") or []) if str(item).strip()])

    overall_decision = "通过"
    if any(item == "驳回" for item in decisions):
        overall_decision = "驳回"
    elif any(item in {"需补充材料", "需更多信息"} for item in decisions):
        overall_decision = "需补充材料"

    return {
        "decision": overall_decision,
        "summary": "；".join(summaries[:8]),
        "item_results": item_results,
        "risks": dedupe_strings(risks),
        "missing_information": dedupe_strings(missing_information),
    }


def persist_run_artifacts(
    run_dir: Path,
    *,
    snapshot: dict[str, Any],
    document: dict[str, Any],
    item_skills: list[dict[str, Any]],
    deterministic_result: dict[str, Any],
    segment_runs: list[dict[str, Any]],
    summary_messages: list[dict[str, str]],
    summary_payload: dict[str, Any],
    summary_result: dict[str, Any] | None,
    final_result: dict[str, Any],
) -> None:
    write_json(run_dir / "project_snapshot.json", snapshot)
    write_json(run_dir / "mapped_document.json", document)
    write_json(run_dir / "approval_item_skills.json", item_skills)
    write_json(run_dir / "rule_engine_baseline.json", deterministic_result)
    write_json(run_dir / "llm_segment_runs.json", segment_runs)
    write_json(run_dir / "llm_summary_messages.json", summary_messages)
    write_json(run_dir / "llm_summary_payload.json", summary_payload)
    if summary_result is not None:
        write_json(run_dir / "llm_summary_response.json", summary_result)
    write_json(run_dir / "approval_result.json", final_result)


def prune_approval_run_history(scene: str, project_id: str, keep_run_dir: Path) -> None:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return
    root_dir = scene_approval_runs_dir(scene)
    try:
        run_dirs = [path for path in root_dir.iterdir() if path.is_dir()]
    except Exception:
        return

    for candidate in run_dirs:
        if candidate.resolve() == keep_run_dir.resolve():
            continue
        result_path = candidate / "approval_result.json"
        if not result_path.exists():
            continue
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("project_id") or "").strip() != normalized_project_id:
            continue
        try:
            shutil.rmtree(candidate)
        except Exception:
            continue


def run_llm_approval(
    *,
    project_name: str,
    project_id: str,
    category: str,
    scene: str = "initiation",
    snapshot: dict[str, Any],
    document: dict[str, Any],
) -> dict[str, Any]:
    normalized_scene = normalize_scene(scene)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = scene_approval_runs_dir(normalized_scene) / f"{timestamp}_{sanitize_name(project_id or project_name)}"
    item_skills = load_item_skill_manifest(category, scene=normalized_scene)
    deterministic_result = evaluate_approval(document=document, category=category, scene=normalized_scene)

    segment_runs: list[dict[str, Any]] = []

    def build_segment_run(skill: dict[str, Any]) -> dict[str, Any]:
        tab_name = str(skill.get("tab") or skill.get("review_point") or "未命名分段")
        messages, payload = build_segment_messages(
            project_name=project_name,
            category=category,
            skill=skill,
            document=document,
            snapshot=snapshot,
            deterministic_result=deterministic_result,
        )
        llm_result = chat_json(messages)
        return {
            "tab": tab_name,
            "skill": compact_skill(skill),
            "payload": payload,
            "messages": messages,
            "response": llm_result,
            "result": llm_result.get("json") or {},
        }

    workers = min(llm_segment_workers(), len(item_skills)) if item_skills else 1
    if workers <= 1:
        segment_runs = [build_segment_run(skill) for skill in item_skills]
    else:
        indexed_runs: dict[int, dict[str, Any]] = {}
        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(build_segment_run, skill): index
                for index, skill in enumerate(item_skills)
            }
            for future in futures.as_completed(future_map):
                index = future_map[future]
                indexed_runs[index] = future.result()
        segment_runs = [indexed_runs[index] for index in sorted(indexed_runs)]
    for skill in []:
        tab_name = str(skill.get("tab") or skill.get("review_point") or "未命名分段")
        messages, payload = build_segment_messages(
            project_name=project_name,
            category=category,
            skill=skill,
            document=document,
            snapshot=snapshot,
            deterministic_result=deterministic_result,
        )
        llm_result = chat_json(messages)
        segment_runs.append(
            {
                "tab": tab_name,
                "skill": compact_skill(skill),
                "payload": payload,
                "messages": messages,
                "response": llm_result,
                "result": llm_result.get("json") or {},
            }
        )

    summary_messages, summary_payload = build_summary_messages(
        project_name=project_name,
        category=category,
        deterministic_result=deterministic_result,
        segment_results=[
            {
                "tab": segment.get("tab"),
                "decision": (segment.get("result") or {}).get("decision"),
                "summary": (segment.get("result") or {}).get("summary"),
                "item_results": (segment.get("result") or {}).get("item_results") or [],
                "risks": (segment.get("result") or {}).get("risks") or [],
                "missing_information": (segment.get("result") or {}).get("missing_information") or [],
            }
            for segment in segment_runs
        ],
    )
    summary_result = chat_json(summary_messages)
    summary_json = summary_result.get("json") or {}
    aggregated = aggregate_segment_results(segment_runs)
    authoritative_item_results = build_authoritative_item_results(deterministic_result, segment_runs)
    authoritative_summary = build_authoritative_summary_v2(deterministic_result)
    authoritative_risks = build_authoritative_risks(deterministic_result)
    authoritative_missing_information = build_authoritative_missing_information(deterministic_result)
    authoritative_positive_evidence = build_authoritative_positive_evidence(deterministic_result)
    authoritative_project_commentary = build_pass_project_commentary(document, deterministic_result)
    final_decision = deterministic_result.get("decision") or summary_json.get("decision") or aggregated["decision"]
    is_pass_decision = str(final_decision or "").strip() == "通过"

    final_result = {
        "project_name": project_name,
        "project_id": project_id,
        "category": category,
        "scene": normalized_scene,
        "document_source": document.get("document_source") or "unknown",
        "document_saved_at": document.get("document_saved_at"),
        "decision": final_decision,
        "summary": authoritative_summary,
        "item_results": authoritative_item_results,
        "risks": [] if is_pass_decision else (authoritative_risks or summary_json.get("risks") or aggregated["risks"]),
        "missing_information": []
        if is_pass_decision
        else (authoritative_missing_information or summary_json.get("missing_information") or aggregated["missing_information"]),
        "positive_evidence": authoritative_positive_evidence,
        "project_commentary": authoritative_project_commentary if is_pass_decision else "",
        "baseline": deterministic_result,
        "segments": [
            {
                "tab": segment.get("tab"),
                "decision": (segment.get("result") or {}).get("decision"),
                "summary": (segment.get("result") or {}).get("summary"),
            }
            for segment in segment_runs
        ],
        "run_dir": str(run_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "decision_source": "baseline_aligned_llm_segmented",
    }

    persist_run_artifacts(
        run_dir,
        snapshot=snapshot,
        document=document,
        item_skills=item_skills,
        deterministic_result=deterministic_result,
        segment_runs=segment_runs,
        summary_messages=summary_messages,
        summary_payload=summary_payload,
        summary_result=summary_result,
        final_result=final_result,
    )
    prune_approval_run_history(normalized_scene, project_id, run_dir)
    return final_result
