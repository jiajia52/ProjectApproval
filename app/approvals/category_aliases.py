"""Canonical aliases for category and review-point naming."""

from __future__ import annotations

from typing import Any

CATEGORY_NAME_ALIASES: dict[str, str] = {
    "系统开发及实施": "工作台开发及实施",
    "系统运维(一、二线)": "大一线运维",
    "系统运维（一、二线）": "大一线运维",
    "系统运维(三线)": "三线运维",
    "系统运维（三线）": "三线运维",
    "系统运维(产品维保)": "产品维保",
    "系统运维（产品维保）": "产品维保",
    "数据订阅及购买": "数据订阅购买",
}

REVIEW_POINT_ALIASES: dict[str, str] = {
    "专业技术领域评审": "专业领域评审",
    "能力(竞争)模型": "能力（竞争）模型",
    "结果(财务/客户)模型": "结果（财务/客户）模型",
}


def normalize_lookup_key(value: Any) -> str:
    text = str(value or "").strip().replace("（", "(").replace("）", ")")
    return "".join(character for character in text if character.isalnum())


def _canonical_name(value: Any, aliases: dict[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in aliases:
        return aliases[text]

    normalized = normalize_lookup_key(text)
    for alias, target in aliases.items():
        if normalize_lookup_key(alias) == normalized:
            return target
    return text


def canonical_category_name(value: Any) -> str:
    return _canonical_name(value, CATEGORY_NAME_ALIASES)


def canonical_review_point(value: Any) -> str:
    return _canonical_name(value, REVIEW_POINT_ALIASES)
