from __future__ import annotations

import re
from typing import Any

from app.approvals.review.category_aliases import canonical_category_name


def normalize_category_key(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(character for character in text if character.isalnum())


def _acceptance_tab_config(
    sections: tuple[str, ...],
    project_review_tabs: tuple[str, ...],
    tam_tabs: tuple[str, ...] = (),
) -> dict[str, list[str]]:
    return {
        "sections": list(sections),
        "project_review_tabs": list(project_review_tabs),
        "tam_tabs": list(tam_tabs),
    }


ACCEPTANCE_FIXED_FULL_SECTIONS = (
    "project_review",
    "acceptance_scope",
    "acceptance_stage",
    "acceptance_detail",
    "acceptance_deliverables",
    "architecture_review",
    "tam_models",
)
ACCEPTANCE_FIXED_ARCHITECTURE_SECTIONS = (
    "project_review",
    "acceptance_scope",
    "acceptance_stage",
    "acceptance_detail",
    "acceptance_deliverables",
    "architecture_review",
)
ACCEPTANCE_FIXED_BASE_SECTIONS = (
    "project_review",
    "acceptance_scope",
    "acceptance_stage",
    "acceptance_detail",
    "acceptance_deliverables",
)
ACCEPTANCE_FIXED_PROJECT_REVIEW_OKR_SYSTEM_SCOPE = (
    "background",
    "okr",
    "scope",
    "system_scope",
    "solution",
    "acceptance_plan",
)
ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_SYSTEM_SCOPE = (
    "background",
    "target",
    "scope",
    "system_scope",
    "solution",
    "acceptance_plan",
)
ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_PANORAMA = (
    "background",
    "target",
    "scope",
    "solution",
    "panorama",
    "annual_model",
    "acceptance_plan",
)
ACCEPTANCE_FIXED_TAM_TABS = ("capability", "result", "management")

ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY: dict[str, dict[str, list[str]]] = {}

for _category_name in (
    "工作台开发及实施",
    "产品运营",
    "系统产品购买",
    "系统开发及运营",
):
    ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key(_category_name)] = _acceptance_tab_config(
        ACCEPTANCE_FIXED_FULL_SECTIONS,
        ACCEPTANCE_FIXED_PROJECT_REVIEW_OKR_SYSTEM_SCOPE,
        ACCEPTANCE_FIXED_TAM_TABS,
    )

for _category_name in (
    "数据订阅购买",
    "设备购买及弱电布线",
    "设备维修",
):
    ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key(_category_name)] = _acceptance_tab_config(
        ACCEPTANCE_FIXED_ARCHITECTURE_SECTIONS,
        ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_PANORAMA,
    )

for _category_name in (
    "大一线运维",
    "三线运维",
    "产品维保",
    "数据中心维护",
    "基础服务",
    "安全服务",
    "数据服务",
    "保密服务",
    "研发工具订阅许可升级",
    "非研发工具订阅许可升级",
    "研发工具许可购买",
    "非研发工具许可购买",
    "资源租赁",
    "机房建设",
):
    ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key(_category_name)] = _acceptance_tab_config(
        ACCEPTANCE_FIXED_BASE_SECTIONS,
        ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_PANORAMA,
    )

ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY[normalize_category_key("对外咨询")] = _acceptance_tab_config(
    ACCEPTANCE_FIXED_BASE_SECTIONS,
    ACCEPTANCE_FIXED_PROJECT_REVIEW_TARGET_SYSTEM_SCOPE,
)


def resolve_acceptance_fixed_tab_config(
    category: Any,
    *,
    default_project_category: str,
) -> dict[str, list[str]]:
    normalized_category = normalize_category_key(canonical_category_name(category))
    default_config = ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY.get(
        normalize_category_key(default_project_category),
        _acceptance_tab_config(
            ACCEPTANCE_FIXED_FULL_SECTIONS,
            ACCEPTANCE_FIXED_PROJECT_REVIEW_OKR_SYSTEM_SCOPE,
            ACCEPTANCE_FIXED_TAM_TABS,
        ),
    )
    config = ACCEPTANCE_FIXED_TAB_CONFIG_BY_CATEGORY_KEY.get(normalized_category, default_config)
    return {
        "sections": list(config["sections"]),
        "project_review_tabs": list(config["project_review_tabs"]),
        "tam_tabs": list(config["tam_tabs"]),
    }


ACCEPTANCE_DYNAMIC_SECTION_KEY_BY_LABEL = {
    "项目回顾": "project_review",
    "专业技术领域评审": "architecture_review",
    "专业技术评审": "architecture_review",
    "tam模型": "tam_models",
    "tam模型评审": "tam_models",
    "验收范围": "acceptance_scope",
    "验收阶段": "acceptance_stage",
    "验收明细": "acceptance_detail",
    "上传备证": "acceptance_deliverables",
    "上传佐证": "acceptance_deliverables",
}

ACCEPTANCE_DYNAMIC_PROJECT_REVIEW_KEY_BY_LABEL = {
    "项目背景": "background",
    "项目目标": "target",
    "项目okr": "okr",
    "项目范围": "scope",
    "系统范围": "system_scope",
    "项目方案": "solution",
    "业务全景图": "panorama",
    "年度管理模型": "annual_model",
    "验收方案": "acceptance_plan",
}

ACCEPTANCE_DYNAMIC_TAM_KEY_BY_LABEL = {
    "能力模型": "capability",
    "能力竞争模型": "capability",
    "结果模型": "result",
    "结果财务客户模型": "result",
    "管理体系模型": "management",
}


def normalize_acceptance_tab_token(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "").strip()).lower()


def normalize_acceptance_tab_config(raw_items: list[dict[str, Any]] | None) -> dict[str, list[str]]:
    def item_order(value: Any) -> tuple[int, int]:
        if not isinstance(value, dict):
            return (1, 10**9)
        candidates = [
            value.get("order"),
            value.get("sort"),
            value.get("sortOrder"),
            value.get("orderNum"),
            value.get("sortNum"),
            value.get("index"),
        ]
        for candidate in candidates:
            try:
                return (0, int(str(candidate).strip()))
            except Exception:
                continue
        return (1, 10**9)

    sections: list[str] = []
    project_review_tabs: list[str] = []
    tam_tabs: list[str] = []
    seen_sections: set[str] = set()
    seen_project_review_tabs: set[str] = set()
    seen_tam_tabs: set[str] = set()

    section_aliases = {
        normalize_acceptance_tab_token(label): key
        for label, key in ACCEPTANCE_DYNAMIC_SECTION_KEY_BY_LABEL.items()
    }
    project_review_aliases = {
        normalize_acceptance_tab_token(label): key
        for label, key in ACCEPTANCE_DYNAMIC_PROJECT_REVIEW_KEY_BY_LABEL.items()
    }
    tam_aliases = {
        normalize_acceptance_tab_token(label): key
        for label, key in ACCEPTANCE_DYNAMIC_TAM_KEY_BY_LABEL.items()
    }

    def collect_item(item: dict[str, Any]) -> None:
        candidates = [
            item.get("label"),
            item.get("name"),
            item.get("text"),
            item.get("title"),
            item.get("tab"),
            item.get("tabName"),
            item.get("classifyName"),
            item.get("reviewPoint"),
            item.get("reviewPointName"),
            item.get("bcName"),
            item.get("content"),
        ]
        for candidate in candidates:
            token = normalize_acceptance_tab_token(candidate)
            if not token:
                continue
            section_key = section_aliases.get(token)
            if section_key and section_key not in seen_sections:
                seen_sections.add(section_key)
                sections.append(section_key)
            project_review_key = project_review_aliases.get(token)
            if project_review_key and project_review_key not in seen_project_review_tabs:
                seen_project_review_tabs.add(project_review_key)
                project_review_tabs.append(project_review_key)
            tam_key = tam_aliases.get(token)
            if tam_key and tam_key not in seen_tam_tabs:
                seen_tam_tabs.add(tam_key)
                tam_tabs.append(tam_key)

    def walk_items(items: list[dict[str, Any]] | None) -> None:
        for item in sorted((items or []), key=item_order):
            if not isinstance(item, dict):
                continue
            collect_item(item)
            for child_key in ("subTabList", "subTabs", "children"):
                child_items = item.get(child_key)
                if isinstance(child_items, list):
                    walk_items(child_items)

    walk_items(raw_items)

    return {
        "sections": sections,
        "project_review_tabs": project_review_tabs,
        "tam_tabs": tam_tabs,
    }
