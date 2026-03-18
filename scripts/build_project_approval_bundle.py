#!/usr/bin/env python3
"""Build the project approval bundle and ontology artifacts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from extract_review_rules import parse_rule_bundle, write_json

DEFAULT_NAMESPACE = "https://faw.example.local/project-approval#"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    return repo_root() / "runtime" / "config" / "skill_config.json"


def default_rule_matrix_path(root: Path | None = None) -> Path:
    active_root = root or repo_root()
    matches = [
        path
        for path in (active_root / "data").glob("*.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    ]
    if not matches:
        raise FileNotFoundError("No .xlsx rule matrix found in data/.")
    preferred_by_name = [
        path
        for path in matches
        if "立项大模型评审规则说明" in path.name and "620标签配置" not in path.name
    ]
    if preferred_by_name:
        return max(preferred_by_name, key=lambda path: (path.stat().st_mtime, path.name))
    non_620_candidates = [path for path in matches if "620标签配置" not in path.name]
    if non_620_candidates:
        return max(non_620_candidates, key=lambda path: (path.stat().st_mtime, path.name))
    preferred = [path for path in matches if "立项大模型评审规则说明" in path.name]
    candidates = preferred or matches
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def parse_markdown_sections(markdown_text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_title: str | None = None
    current_level = 0
    buffer: list[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            if current_title is not None:
                sections.append({"level": current_level, "title": current_title, "content": "\n".join(buffer).strip()})
            current_level = len(match.group(1))
            current_title = match.group(2).strip()
            buffer = []
        elif current_title is not None:
            buffer.append(line)
    if current_title is not None:
        sections.append({"level": current_level, "title": current_title, "content": "\n".join(buffer).strip()})
    return sections


def extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            bullets.append(re.sub(r"^[-*]\s+|^\d+\.\s+", "", stripped))
    return bullets


def parse_api_list(path: Path) -> dict[str, Any]:
    base_url = ""
    endpoints: list[dict[str, Any]] = []
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("base_url="):
            base_url = line.split("=", 1)[1].strip()
            continue
        url_match = re.search(r"https?://[^\s]+", line)
        path_match = re.search(r"(/[A-Za-z0-9_./{}-]+)", line)
        if not url_match and not path_match:
            if endpoints:
                endpoints[-1]["notes"].append(line)
            continue
        name = re.split(r"[:：]", line, maxsplit=1)[0].strip()
        endpoint = ""
        if url_match:
            endpoint = re.sub(r"^https?://[^/]+", "", url_match.group(0))
        elif path_match:
            endpoint = path_match.group(1)
        endpoints.append({"name": name, "endpoint": endpoint, "notes": [line]})
    return {"base_url": base_url, "endpoints": endpoints}


def sanitize_identifier(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", str(value or "")).strip()
    if not cleaned:
        return "Item"
    return "".join(part.capitalize() for part in cleaned.split())


def collect_frontend_pages(root: Path) -> list[dict[str, Any]]:
    pages_dir = root / "frontend" / "src" / "pages"
    route_map = {
        "ApprovalPage": "/approval",
        "ReviewFeedbackPage": "/review-feedback",
        "ProjectViewerPage": "/project/:projectId",
        "WorkbenchPage": "/workbench",
        "SkillsPage": "/skills",
    }
    label_map = {
        "ApprovalPage": "审批首页",
        "ReviewFeedbackPage": "建议复核页",
        "ProjectViewerPage": "项目详情页",
        "WorkbenchPage": "审批工作台",
        "SkillsPage": "技能与规则页",
    }
    pages: list[dict[str, Any]] = []
    for index, path in enumerate(sorted(pages_dir.glob("*Page.jsx")), start=1):
        name = path.stem
        pages.append(
            {
                "id": f"FrontendPage{index:02d}",
                "label": label_map.get(name, name),
                "component": name,
                "route": route_map.get(name, ""),
                "source_path": str(path.relative_to(root)).replace("\\", "/"),
            }
        )
    return pages


def collect_backend_routes(root: Path) -> list[dict[str, Any]]:
    main_path = root / "app" / "main.py"
    if not main_path.exists():
        return []
    lines = main_path.read_text(encoding="utf-8").splitlines()
    routes: list[dict[str, Any]] = []
    pending: dict[str, str] | None = None
    for line in lines:
        route_match = re.search(r'@app\.(get|post|put|delete)\("([^"]+)"', line)
        if route_match:
            pending = {"method": route_match.group(1).upper(), "path": route_match.group(2)}
            continue
        if pending is not None:
            handler_match = re.match(r"def\s+([A-Za-z0-9_]+)\(", line.strip())
            if handler_match:
                handler = handler_match.group(1)
                routes.append(
                    {
                        "id": f"BackendRoute{len(routes)+1:02d}",
                        "label": pending["path"],
                        "path": pending["path"],
                        "method": pending["method"],
                        "handler": handler,
                    }
                )
                pending = None
    return routes


def collect_backend_services(root: Path) -> list[dict[str, Any]]:
    service_files = [
        root / "desktop_launcher.py",
        root / "app" / "main.py",
        root / "app" / "approvals" / "approval_engine.py",
        root / "app" / "approvals" / "llm_approval_service.py",
        root / "app" / "approvals" / "iwork_client.py",
        root / "app" / "approvals" / "remote_project_mapper.py",
        root / "app" / "approvals" / "project_document_store.py",
        root / "app" / "approvals" / "review_feedback_store.py",
        root / "app" / "core" / "startup_checks.py",
    ]
    label_map = {
        "desktop_launcher.py": "桌面启动器",
        "main.py": "FastAPI 应用入口",
        "approval_engine.py": "规则审批引擎",
        "llm_approval_service.py": "大模型审批服务",
        "iwork_client.py": "远程项目接口客户端",
        "remote_project_mapper.py": "远程项目文档映射器",
        "project_document_store.py": "项目文档落盘服务",
        "review_feedback_store.py": "人工复核落盘服务",
        "startup_checks.py": "启动检查服务",
    }
    services: list[dict[str, Any]] = []
    for index, path in enumerate([item for item in service_files if item.exists()], start=1):
        services.append(
            {
                "id": f"BackendService{index:02d}",
                "label": label_map.get(path.name, path.stem),
                "module": str(path.relative_to(root)).replace("\\", "/"),
                "service_type": "launcher" if path.name == "desktop_launcher.py" else "backend",
            }
        )
    return services


def collect_runtime_artifacts(root: Path) -> list[dict[str, Any]]:
    runtime_dir = root / "runtime"
    if not runtime_dir.exists():
        return []
    selected_names = {
        "config",
        "logs",
        "approval_runs",
        "api_result",
        "api_dumps",
        "project_documents",
        "review_feedback",
        "review_rules.json",
        "project_approval_project.json",
        "project_approval_ontology.json",
        "project_approval_ontology.ttl",
        "startup_checks.json",
        "latest_approval_result.json",
        "latest_project_document.json",
    }
    artifacts: list[dict[str, Any]] = []
    for index, path in enumerate(sorted(item for item in runtime_dir.iterdir() if item.name in selected_names), start=1):
        artifacts.append(
            {
                "id": f"RuntimeArtifact{index:02d}",
                "label": path.name,
                "artifact_type": "directory" if path.is_dir() else "file",
                "path": str(path.relative_to(root)).replace("\\", "/"),
            }
        )
    return artifacts


def collect_configuration_files(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        root / ".env.example",
        root / "runtime" / "config" / "skill_config.json",
        root / "runtime" / "config" / "integration_config.json",
        resolve_path(root, config["sources"]["product_info"]),
        resolve_path(root, config["sources"]["api_list"]),
        resolve_path(root, config["sources"]["rule_matrix"]),
    ]
    labels = {
        ".env.example": "环境变量模板",
        "skill_config.json": "系统生成配置",
        "integration_config.json": "远程接口配置",
    }
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, path in enumerate([item for item in candidates if item.exists()], start=1):
        rel_path = str(path.relative_to(root)).replace("\\", "/")
        if rel_path in seen:
            continue
        seen.add(rel_path)
        items.append(
            {
                "id": f"ConfigFile{index:02d}",
                "label": labels.get(path.name, path.name),
                "config_type": path.suffix.lstrip(".") or "env",
                "path": rel_path,
            }
        )
    return items


def collect_approval_skills(root: Path) -> list[dict[str, Any]]:
    manifest_path = root / "skills" / "manifest.json"
    if not manifest_path.exists():
        return []
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = []
    for index, skill in enumerate(payload.get("skills", []), start=1):
        items.append(
            {
                "id": f"ApprovalSkill{index:02d}",
                "label": skill.get("skill_name") or skill.get("review_point") or f"Skill{index}",
                "tab": skill.get("tab") or skill.get("review_point") or "",
                "rule_count": int(skill.get("rule_count") or 0),
            }
        )
    return items


def collect_deployment_packages(root: Path) -> list[dict[str, Any]]:
    packages = [
        {
            "id": "DeploymentPackage01",
            "label": "Windows Portable Package",
            "package_type": "windows-portable",
            "entry": "ProjectApproval.exe",
        },
        {
            "id": "DeploymentPackage02",
            "label": "Linux Offline Bundle",
            "package_type": "linux-offline",
            "entry": "run.sh",
        },
    ]
    return packages


def build_system_inventory(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": {
            "id": "System01",
            "label": config["generation"]["generated_project_name"],
            "entry_ui": "/ui/approval",
        },
        "frontend_pages": collect_frontend_pages(root),
        "backend_routes": collect_backend_routes(root),
        "backend_services": collect_backend_services(root),
        "runtime_artifacts": collect_runtime_artifacts(root),
        "configuration_files": collect_configuration_files(root, config),
        "approval_skills": collect_approval_skills(root),
        "deployment_packages": collect_deployment_packages(root),
    }


def default_config(rules_bundle: dict[str, Any]) -> dict[str, Any]:
    categories = [item["name"] for item in rules_bundle["categories"]]
    review_points: list[str] = []
    seen: set[str] = set()
    for rule in rules_bundle["rules"]:
        review_point = (rule.get("review_point") or "").strip()
        if review_point and review_point not in seen:
            seen.add(review_point)
            review_points.append(review_point)
    return {
        "skill": {
            "name": "project-approval",
            "display_name": "Project Approval",
            "description": "根据 product_info、API 列表和规则矩阵生成立项审批项目与本体文件。",
            "default_prompt": "Generate project approval bundle artifacts from local project data and review rules.",
        },
        "sources": {
            "product_info": "data/product_info.md",
            "api_list": "data/API列表.txt",
            "rule_matrix": f"data/{default_rule_matrix_path().name}",
        },
        "generation": {
            "output_dir": "runtime",
            "rules_output": "runtime/review_rules.json",
            "ontology_namespace": DEFAULT_NAMESPACE,
            "enabled_categories": categories,
            "enabled_skill_groups": review_points,
            "decision_levels": ["通过", "需补充材料", "驳回"],
            "generated_project_name": "项目立项自动审批系统",
        },
    }


def normalize_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").lstrip("./")
    if normalized in {"generated", "runtime"}:
        return "runtime"
    if normalized in {"resources", "data"}:
        return "data"
    if normalized in {"config", "runtime/config"}:
        return "runtime/config"
    if normalized.startswith(("backend/resources/", "resources/")):
        return f"data/{Path(normalized).name}"
    if normalized.startswith(("backend/generated/", "generated/")):
        return f"runtime/{Path(normalized).name}"
    if normalized.startswith(("backend/config/", "config/")):
        return f"runtime/config/{Path(normalized).name}"
    return normalized


def normalize_config(config: dict[str, Any], rules_bundle: dict[str, Any]) -> dict[str, Any]:
    merged = default_config(rules_bundle)
    merged["skill"].update(config.get("skill", {}))
    merged["sources"].update(config.get("sources", {}))
    merged["generation"].update(config.get("generation", {}))
    merged["sources"]["product_info"] = normalize_relative_path(merged["sources"]["product_info"])
    merged["sources"]["api_list"] = normalize_relative_path(merged["sources"]["api_list"])
    merged["sources"]["rule_matrix"] = normalize_relative_path(merged["sources"]["rule_matrix"])
    merged["generation"]["output_dir"] = normalize_relative_path(merged["generation"]["output_dir"])
    merged["generation"]["rules_output"] = normalize_relative_path(merged["generation"]["rules_output"])
    if merged["skill"].get("name") == "project-approval-generator":
        merged["skill"] = default_config(rules_bundle)["skill"]
    if not merged["generation"].get("enabled_skill_groups"):
        merged["generation"]["enabled_skill_groups"] = default_config(rules_bundle)["generation"]["enabled_skill_groups"]
    return merged


def load_or_create_config(config_path: Path, root: Path, rules_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    active_rules_bundle = rules_bundle or parse_rule_bundle(default_rule_matrix_path(root))
    if config_path.exists():
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        config = normalize_config(raw_config, active_rules_bundle)
        if config != raw_config:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config
    config = default_config(active_rules_bundle)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def resolve_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return root / value


def resolve_rule_matrix_path(root: Path, config: dict[str, Any]) -> Path:
    configured = config.get("sources", {}).get("rule_matrix")
    if configured:
        return resolve_path(root, configured)
    return default_rule_matrix_path(root)


def filter_rules(
    rules_bundle: dict[str, Any],
    enabled_categories: set[str],
    enabled_skill_groups: set[str],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for rule in rules_bundle["rules"]:
        review_point = (rule.get("review_point") or "").strip()
        if enabled_skill_groups and review_point not in enabled_skill_groups:
            continue
        categories = {item["category"] for item in rule["applicable_categories"]}
        if not categories or categories & enabled_categories:
            filtered.append(rule)
    return filtered


def build_project_definition(sections: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    top_sections = [section for section in sections if section["level"] == 2]
    scope_sections = [section for section in sections if section["level"] == 3]

    def top_content(index: int) -> str:
        return top_sections[index]["content"] if len(top_sections) > index else ""

    def top_title(index: int) -> str:
        return top_sections[index]["title"] if len(top_sections) > index else config["generation"]["generated_project_name"]

    goals = extract_bullets(top_content(2)) or extract_bullets(top_content(2).replace("    ", "\n"))
    scope_included = extract_bullets(scope_sections[0]["content"]) if len(scope_sections) > 0 else []
    scope_excluded = extract_bullets(scope_sections[1]["content"]) if len(scope_sections) > 1 else []
    return {
        "name": config["generation"]["generated_project_name"],
        "title": top_title(0),
        "overview": top_content(0),
        "background": top_content(1),
        "goals": goals,
        "scope_included": scope_included,
        "scope_excluded": scope_excluded,
        "technical_solution": top_content(4),
        "architecture": top_content(5),
        "implementation_plan": top_content(6),
        "project_value": top_content(7),
        "risk_response": top_content(8),
        "operations": top_content(9),
        "example_result": top_content(10),
    }


def build_ontology(
    project_definition: dict[str, Any],
    api_bundle: dict[str, Any],
    rules_bundle: dict[str, Any],
    filtered_rules: list[dict[str, Any]],
    config: dict[str, Any],
    system_inventory: dict[str, Any],
) -> dict[str, Any]:
    namespace = config["generation"].get("ontology_namespace", DEFAULT_NAMESPACE)
    return {
        "namespace": namespace,
        "title": project_definition["name"],
        "classes": [
            {"id": "ProjectApprovalSystem", "label": "项目审批系统", "description": "覆盖前端、后端、运行时资产与分发包的完整审批平台。"},
            {"id": "ProjectApprovalProject", "label": "立项审批项目", "description": "项目审批场景下的根实体。"},
            {"id": "ProjectContent", "label": "项目内容", "description": "项目背景、目标、方案等申报内容。"},
            {"id": "ProjectOKR", "label": "项目OKR", "description": "项目目标、关键结果及相关信息。"},
            {"id": "ProjectScope", "label": "项目范围", "description": "业务范围与系统范围信息。"},
            {"id": "ArchitectureReview", "label": "架构评审", "description": "业务、数据、技术、安全等架构评审维度。"},
            {"id": "ProjectValuePlan", "label": "项目价值与计划", "description": "项目价值模型、里程碑及相关计划信息。"},
            {"id": "OrganizationBudget", "label": "组织与预算", "description": "组织架构、预算与费用信息。"},
            {"id": "ReviewRule", "label": "评审规则", "description": "从规则矩阵中抽取的审批规则。"},
            {"id": "ApiEndpoint", "label": "远程接口", "description": "项目数据来源接口。"},
            {"id": "BackendApiRoute", "label": "后端路由", "description": "本地审批系统暴露的 HTTP 路由。"},
            {"id": "FrontendPage", "label": "前端页面", "description": "系统面向用户的前端页面。"},
            {"id": "BackendService", "label": "后端服务", "description": "系统中的后端模块或运行服务。"},
            {"id": "RuntimeArtifact", "label": "运行时资产", "description": "系统运行过程中生成或依赖的文件与目录。"},
            {"id": "ConfigurationFile", "label": "配置文件", "description": "系统运行依赖的配置输入文件。"},
            {"id": "ApprovalSkill", "label": "审批技能", "description": "按审批 tab 聚合生成的技能单元。"},
            {"id": "DeploymentPackage", "label": "部署包", "description": "面向目标操作系统的分发包。"},
            {"id": "ProjectCategory", "label": "项目品类", "description": "适用的项目分类。"},
            {"id": "ApprovalDecision", "label": "审批结论", "description": "审批结果等级。"},
        ],
        "object_properties": [
            {"id": "hasFrontendPage", "label": "包含前端页面", "domain": "ProjectApprovalSystem", "range": "FrontendPage"},
            {"id": "exposesBackendRoute", "label": "暴露后端路由", "domain": "ProjectApprovalSystem", "range": "BackendApiRoute"},
            {"id": "usesBackendService", "label": "使用后端服务", "domain": "ProjectApprovalSystem", "range": "BackendService"},
            {"id": "persistsArtifact", "label": "持久化运行资产", "domain": "ProjectApprovalSystem", "range": "RuntimeArtifact"},
            {"id": "usesConfigurationFile", "label": "使用配置文件", "domain": "ProjectApprovalSystem", "range": "ConfigurationFile"},
            {"id": "loadsApprovalSkill", "label": "加载审批技能", "domain": "ProjectApprovalSystem", "range": "ApprovalSkill"},
            {"id": "packagedAs", "label": "打包为", "domain": "ProjectApprovalSystem", "range": "DeploymentPackage"},
            {"id": "hasContent", "label": "包含项目内容", "domain": "ProjectApprovalProject", "range": "ProjectContent"},
            {"id": "hasOKR", "label": "包含项目OKR", "domain": "ProjectApprovalProject", "range": "ProjectOKR"},
            {"id": "hasScope", "label": "包含项目范围", "domain": "ProjectApprovalProject", "range": "ProjectScope"},
            {"id": "hasArchitectureReview", "label": "包含架构评审", "domain": "ProjectApprovalProject", "range": "ArchitectureReview"},
            {"id": "hasValuePlan", "label": "包含价值与计划", "domain": "ProjectApprovalProject", "range": "ProjectValuePlan"},
            {"id": "hasOrganizationBudget", "label": "包含组织与预算", "domain": "ProjectApprovalProject", "range": "OrganizationBudget"},
            {"id": "usesApiEndpoint", "label": "使用远程接口", "domain": "ProjectApprovalProject", "range": "ApiEndpoint"},
            {"id": "appliesRule", "label": "应用评审规则", "domain": "ProjectApprovalProject", "range": "ReviewRule"},
            {"id": "targetsCategory", "label": "适用品类", "domain": "ReviewRule", "range": "ProjectCategory"},
            {"id": "hasDecisionLevel", "label": "具有审批结论", "domain": "ProjectApprovalProject", "range": "ApprovalDecision"},
        ],
        "data_properties": [
            {"id": "systemEntryUrl", "label": "系统入口地址", "domain": "ProjectApprovalSystem", "range": "xsd:string"},
            {"id": "projectTitle", "label": "项目标题", "domain": "ProjectApprovalProject", "range": "xsd:string"},
            {"id": "sectionSummary", "label": "内容摘要", "domain": "ProjectContent", "range": "xsd:string"},
            {"id": "reviewPointName", "label": "评审点名称", "domain": "ReviewRule", "range": "xsd:string"},
            {"id": "ruleText", "label": "规则文本", "domain": "ReviewRule", "range": "xsd:string"},
            {"id": "apiPath", "label": "接口路径", "domain": "ApiEndpoint", "range": "xsd:string"},
            {"id": "routePath", "label": "路由路径", "domain": "FrontendPage", "range": "xsd:string"},
            {"id": "componentName", "label": "组件名称", "domain": "FrontendPage", "range": "xsd:string"},
            {"id": "httpMethod", "label": "请求方法", "domain": "BackendApiRoute", "range": "xsd:string"},
            {"id": "handlerName", "label": "处理函数", "domain": "BackendApiRoute", "range": "xsd:string"},
            {"id": "modulePath", "label": "模块路径", "domain": "BackendService", "range": "xsd:string"},
            {"id": "serviceType", "label": "服务类型", "domain": "BackendService", "range": "xsd:string"},
            {"id": "artifactPath", "label": "资产路径", "domain": "RuntimeArtifact", "range": "xsd:string"},
            {"id": "artifactType", "label": "资产类型", "domain": "RuntimeArtifact", "range": "xsd:string"},
            {"id": "configPath", "label": "配置路径", "domain": "ConfigurationFile", "range": "xsd:string"},
            {"id": "configType", "label": "配置类型", "domain": "ConfigurationFile", "range": "xsd:string"},
            {"id": "skillTab", "label": "技能页签", "domain": "ApprovalSkill", "range": "xsd:string"},
            {"id": "skillRuleCount", "label": "技能规则数量", "domain": "ApprovalSkill", "range": "xsd:integer"},
            {"id": "packageType", "label": "部署包类型", "domain": "DeploymentPackage", "range": "xsd:string"},
            {"id": "packageEntry", "label": "启动入口", "domain": "DeploymentPackage", "range": "xsd:string"},
            {"id": "categoryGroup", "label": "品类分组", "domain": "ProjectCategory", "range": "xsd:string"},
            {"id": "decisionLabel", "label": "结论标签", "domain": "ApprovalDecision", "range": "xsd:string"},
        ],
        "individuals": {
            "systems": [system_inventory["system"]],
            "categories": [
                {"id": f"Category{index:02d}", "label": category["name"], "group": category["group"]}
                for index, category in enumerate(rules_bundle["categories"], start=1)
            ],
            "decisions": [
                {"id": f"Decision{index:02d}", "label": level}
                for index, level in enumerate(config["generation"]["decision_levels"], start=1)
            ],
            "api_endpoints": [
                {"id": f"ApiEndpoint{index:02d}", "label": endpoint["name"], "path": endpoint["endpoint"], "notes": endpoint["notes"]}
                for index, endpoint in enumerate(api_bundle["endpoints"], start=1)
            ],
            "frontend_pages": system_inventory["frontend_pages"],
            "backend_routes": system_inventory["backend_routes"],
            "backend_services": system_inventory["backend_services"],
            "runtime_artifacts": system_inventory["runtime_artifacts"],
            "configuration_files": system_inventory["configuration_files"],
            "approval_skills": system_inventory["approval_skills"],
            "deployment_packages": system_inventory["deployment_packages"],
        },
        "system_links": {
            "frontend_pages": [item["id"] for item in system_inventory["frontend_pages"]],
            "backend_routes": [item["id"] for item in system_inventory["backend_routes"]],
            "backend_services": [item["id"] for item in system_inventory["backend_services"]],
            "runtime_artifacts": [item["id"] for item in system_inventory["runtime_artifacts"]],
            "configuration_files": [item["id"] for item in system_inventory["configuration_files"]],
            "approval_skills": [item["id"] for item in system_inventory["approval_skills"]],
            "deployment_packages": [item["id"] for item in system_inventory["deployment_packages"]],
        },
        "statistics": {
            "api_count": len(api_bundle["endpoints"]),
            "rule_count": len(rules_bundle["rules"]),
            "enabled_rule_count": len(filtered_rules),
            "category_count": len(rules_bundle["categories"]),
            "enabled_skill_group_count": len(config["generation"].get("enabled_skill_groups", [])),
            "frontend_page_count": len(system_inventory["frontend_pages"]),
            "backend_route_count": len(system_inventory["backend_routes"]),
            "backend_service_count": len(system_inventory["backend_services"]),
            "runtime_artifact_count": len(system_inventory["runtime_artifacts"]),
            "configuration_file_count": len(system_inventory["configuration_files"]),
            "approval_skill_count": len(system_inventory["approval_skills"]),
        },
    }


def render_ontology_ttl(ontology: dict[str, Any]) -> str:
    lines = [
        f"@prefix pa: <{ontology['namespace']}> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        "pa:ProjectApprovalOntology a owl:Ontology ;",
        f'  rdfs:label "{ontology["title"]}" .',
        "",
    ]
    for class_spec in ontology["classes"]:
        lines.extend(
            [
                f"pa:{class_spec['id']} a owl:Class ;",
                f'  rdfs:label "{class_spec["label"]}" ;',
                f'  rdfs:comment "{class_spec["description"]}" .',
                "",
            ]
        )
    for property_spec in ontology["object_properties"]:
        lines.extend(
            [
                f"pa:{property_spec['id']} a owl:ObjectProperty ;",
                f"  rdfs:domain pa:{property_spec['domain']} ;",
                f"  rdfs:range pa:{property_spec['range']} ;",
                f'  rdfs:label "{property_spec["label"]}" .',
                "",
            ]
        )
    for property_spec in ontology["data_properties"]:
        lines.extend(
            [
                f"pa:{property_spec['id']} a owl:DatatypeProperty ;",
                f"  rdfs:domain pa:{property_spec['domain']} ;",
                f"  rdfs:range {property_spec['range']} ;",
                f'  rdfs:label "{property_spec["label"]}" .',
                "",
            ]
        )
    for system in ontology["individuals"].get("systems", []):
        system_properties = [
            f'  rdfs:label "{system["label"]}"',
            f'  pa:systemEntryUrl "{system.get("entry_ui", "")}"',
        ]
        for predicate, key in [
            ("hasFrontendPage", "frontend_pages"),
            ("exposesBackendRoute", "backend_routes"),
            ("usesBackendService", "backend_services"),
            ("persistsArtifact", "runtime_artifacts"),
            ("usesConfigurationFile", "configuration_files"),
            ("loadsApprovalSkill", "approval_skills"),
            ("packagedAs", "deployment_packages"),
        ]:
            for item_id in ontology.get("system_links", {}).get(key, []):
                system_properties.append(f"  pa:{predicate} pa:{item_id}")
        lines.append(f"pa:{system['id']} a owl:NamedIndividual , pa:ProjectApprovalSystem ;")
        for index, item in enumerate(system_properties):
            suffix = " ." if index == len(system_properties) - 1 else " ;"
            lines.append(f"{item}{suffix}")
        lines.append("")
    for category in ontology["individuals"]["categories"]:
        lines.extend(
            [
                f"pa:{category['id']} a owl:NamedIndividual , pa:ProjectCategory ;",
                f'  rdfs:label "{category["label"]}" ;',
                f'  pa:categoryGroup "{category["group"]}" .',
                "",
            ]
        )
    for decision in ontology["individuals"]["decisions"]:
        lines.extend(
            [
                f"pa:{decision['id']} a owl:NamedIndividual , pa:ApprovalDecision ;",
                f'  rdfs:label "{decision["label"]}" ;',
                f'  pa:decisionLabel "{decision["label"]}" .',
                "",
            ]
        )
    for endpoint in ontology["individuals"]["api_endpoints"]:
        lines.extend(
            [
                f"pa:{endpoint['id']} a owl:NamedIndividual , pa:ApiEndpoint ;",
                f'  rdfs:label "{endpoint["label"]}" ;',
                f'  pa:apiPath "{endpoint["path"] or ""}" .',
                "",
            ]
        )
    for page in ontology["individuals"].get("frontend_pages", []):
        lines.extend(
            [
                f"pa:{page['id']} a owl:NamedIndividual , pa:FrontendPage ;",
                f'  rdfs:label "{page["label"]}" ;',
                f'  pa:routePath "{page.get("route", "")}" ;',
                f'  pa:componentName "{page.get("component", "")}" .',
                "",
            ]
        )
    for route in ontology["individuals"].get("backend_routes", []):
        lines.extend(
            [
                f"pa:{route['id']} a owl:NamedIndividual , pa:BackendApiRoute ;",
                f'  rdfs:label "{route["label"]}" ;',
                f'  pa:routePath "{route.get("path", "")}" ;',
                f'  pa:httpMethod "{route.get("method", "")}" ;',
                f'  pa:handlerName "{route.get("handler", "")}" .',
                "",
            ]
        )
    for service in ontology["individuals"].get("backend_services", []):
        lines.extend(
            [
                f"pa:{service['id']} a owl:NamedIndividual , pa:BackendService ;",
                f'  rdfs:label "{service["label"]}" ;',
                f'  pa:modulePath "{service.get("module", "")}" ;',
                f'  pa:serviceType "{service.get("service_type", "")}" .',
                "",
            ]
        )
    for artifact in ontology["individuals"].get("runtime_artifacts", []):
        lines.extend(
            [
                f"pa:{artifact['id']} a owl:NamedIndividual , pa:RuntimeArtifact ;",
                f'  rdfs:label "{artifact["label"]}" ;',
                f'  pa:artifactPath "{artifact.get("path", "")}" ;',
                f'  pa:artifactType "{artifact.get("artifact_type", "")}" .',
                "",
            ]
        )
    for item in ontology["individuals"].get("configuration_files", []):
        lines.extend(
            [
                f"pa:{item['id']} a owl:NamedIndividual , pa:ConfigurationFile ;",
                f'  rdfs:label "{item["label"]}" ;',
                f'  pa:configPath "{item.get("path", "")}" ;',
                f'  pa:configType "{item.get("config_type", "")}" .',
                "",
            ]
        )
    for skill in ontology["individuals"].get("approval_skills", []):
        lines.extend(
            [
                f"pa:{skill['id']} a owl:NamedIndividual , pa:ApprovalSkill ;",
                f'  rdfs:label "{skill["label"]}" ;',
                f'  pa:skillTab "{skill.get("tab", "")}" ;',
                f"  pa:skillRuleCount {skill.get('rule_count', 0)} .",
                "",
            ]
        )
    for package in ontology["individuals"].get("deployment_packages", []):
        lines.extend(
            [
                f"pa:{package['id']} a owl:NamedIndividual , pa:DeploymentPackage ;",
                f'  rdfs:label "{package["label"]}" ;',
                f'  pa:packageType "{package.get("package_type", "")}" ;',
                f'  pa:packageEntry "{package.get("entry", "")}" .',
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_project_bundle(root: Path | None = None, config_path: Path | None = None) -> dict[str, Any]:
    active_root = root or repo_root()
    active_config_path = config_path or default_config_path()
    bootstrap_rules = parse_rule_bundle(default_rule_matrix_path(active_root))
    config = load_or_create_config(active_config_path, active_root, bootstrap_rules)
    rules_bundle = parse_rule_bundle(resolve_rule_matrix_path(active_root, config))

    product_path = resolve_path(active_root, config["sources"]["product_info"])
    api_list_path = resolve_path(active_root, config["sources"]["api_list"])
    output_dir = resolve_path(active_root, config["generation"]["output_dir"])
    rules_output = resolve_path(active_root, config["generation"]["rules_output"])
    output_dir.mkdir(parents=True, exist_ok=True)

    sections = parse_markdown_sections(read_text(product_path))
    api_bundle = parse_api_list(api_list_path)
    enabled_categories = set(config["generation"].get("enabled_categories", []))
    enabled_skill_groups = set(config["generation"].get("enabled_skill_groups", []))
    filtered_rules = filter_rules(rules_bundle, enabled_categories, enabled_skill_groups)
    project_definition = build_project_definition(sections, config)
    system_inventory = build_system_inventory(active_root, config)
    ontology = build_ontology(project_definition, api_bundle, rules_bundle, filtered_rules, config, system_inventory)
    ontology_ttl = render_ontology_ttl(ontology)

    project_bundle = {
        "generated_at": datetime.now(UTC).isoformat(),
        "skill": config["skill"],
        "sources": config["sources"],
        "project_definition": project_definition,
        "system_inventory": system_inventory,
        "api_bundle": api_bundle,
        "review_rules": filtered_rules,
        "ontology": ontology,
        "statistics": {
            "section_count": len(sections),
            "api_count": len(api_bundle["endpoints"]),
            "total_rule_count": len(rules_bundle["rules"]),
            "enabled_rule_count": len(filtered_rules),
            "enabled_skill_group_count": len(enabled_skill_groups),
        },
    }

    project_output = output_dir / "project_approval_project.json"
    ontology_json_output = output_dir / "project_approval_ontology.json"
    ontology_ttl_output = output_dir / "project_approval_ontology.ttl"

    write_json(rules_output, rules_bundle)
    write_json(project_output, project_bundle)
    write_json(ontology_json_output, ontology)
    ontology_ttl_output.write_text(ontology_ttl, encoding="utf-8")

    return {
        "config": config,
        "project_bundle": project_bundle,
        "files": {
            "rules": str(rules_output),
            "project": str(project_output),
            "ontology_json": str(ontology_json_output),
            "ontology_ttl": str(ontology_ttl_output),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate project approval bundle artifacts.")
    parser.add_argument("--config", default=str(default_config_path()), help="Path to the JSON config file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_project_bundle(config_path=Path(args.config))
    print(json.dumps(result["files"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
