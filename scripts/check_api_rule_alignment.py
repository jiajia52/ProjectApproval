#!/usr/bin/env python3
"""Check alignment between 620 API tag config and review-rule matrix."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from extract_review_rules import parse_rule_bundle

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CATEGORY_ALIAS_SUGGESTIONS = {
    "系统开发及实施": "工作台开发及实施",
    "系统运维(一、二线)": "大一线运维",
    "系统运维(三线)": "三线运维",
    "系统运维（三线）": "三线运维",
    "系统运维(产品维保)": "产品维保",
    "系统运维（产品维保）": "产品维保",
    "数据订阅及购买": "数据订阅购买",
}

REVIEW_POINT_ALIAS_SUGGESTIONS = {
    "专业技术领域评审": "专业领域评审",
    "能力(竞争)模型": "能力（竞争）模型",
    "结果(财务/客户)模型": "结果（财务/客户）模型",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_lookup_key(value: Any) -> str:
    text = normalize_text(value).replace("（", "(").replace("）", ")")
    return "".join(ch for ch in text if ch.isalnum())


def resolve_620_path(path: str | None = None) -> Path:
    if path:
        return Path(path)
    candidates = [p for p in (repo_root() / "data").glob("*.xlsx") if "620标签配置" in p.name and not p.name.startswith("~$")]
    if not candidates:
        raise FileNotFoundError("620标签配置 xlsx not found in data/.")
    preferred = [p for p in candidates if "260316" in p.name]
    return max(preferred or candidates, key=lambda p: (p.stat().st_mtime, p.name))


def resolve_rule_path(path: str | None = None) -> Path:
    if path:
        return Path(path)
    candidates = [
        p
        for p in (repo_root() / "data").glob("*.xlsx")
        if "立项大模型评审规则说明" in p.name and not p.name.startswith("~$")
    ]
    if not candidates:
        raise FileNotFoundError("立项大模型评审规则说明 xlsx not found in data/.")
    preferred = [p for p in candidates if "3-13" in p.name]
    return max(preferred or candidates, key=lambda p: (p.stat().st_mtime, p.name))


def read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root:
        values.append("".join((node.text or "") for node in item.iter(f"{{{SPREADSHEET_NS}}}t")))
    return values


def cell_value(cell: ET.Element, shared: list[str]) -> str:
    value_node = cell.find(f"{{{SPREADSHEET_NS}}}v")
    if value_node is None:
        return ""
    value = value_node.text or ""
    if cell.attrib.get("t") == "s":
        try:
            return shared[int(value)].strip()
        except Exception:
            return value.strip()
    return value.strip()


def extract_column(ref: str) -> str:
    return "".join(ch for ch in ref if ch.isalpha())


def split_endpoint_expression(value: str) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    candidates = []
    for line in text.splitlines():
        endpoint = normalize_text(re.sub(r"^\d+[、.)]\s*", "", line))
        if not endpoint:
            continue
        match = re.search(r"(/[A-Za-z0-9_./{}?=&-]+)", endpoint)
        if match:
            endpoint = match.group(1)
        if endpoint.startswith("/"):
            candidates.append(endpoint)
    return list(dict.fromkeys(candidates))


def parse_620_records(xlsx_path: Path) -> list[dict[str, Any]]:
    with ZipFile(xlsx_path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relationships = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheets = workbook.find(f"{{{SPREADSHEET_NS}}}sheets")
        if sheets is None or not len(sheets):
            return []
        first_sheet = sheets[0]
        target = relationships[first_sheet.attrib[f"{{{REL_NS}}}id"]]
        worksheet = ET.fromstring(zf.read(f"xl/{target}"))
        sheet_data = worksheet.find(f"{{{SPREADSHEET_NS}}}sheetData")
        if sheet_data is None:
            return []
        shared = read_shared_strings(zf)

        rows: list[dict[str, str]] = []
        for row in sheet_data:
            row_data: dict[str, str] = {}
            for cell in row:
                column = extract_column(cell.attrib.get("r", ""))
                if not column:
                    continue
                row_data[column] = cell_value(cell, shared)
            rows.append(row_data)

    carry = {column: "" for column in ["A", "B", "C", "D"]}
    parsed: list[dict[str, Any]] = []
    for row in rows[1:]:
        for column in ["A", "B", "C", "D"]:
            value = normalize_text(row.get(column, ""))
            if value:
                carry[column] = value
        endpoint_expr = normalize_text(row.get("E", ""))
        if not endpoint_expr:
            continue
        endpoints = split_endpoint_expression(endpoint_expr)
        for endpoint in endpoints:
            parsed.append(
                {
                    "business_category": carry["A"],
                    "business_subcategory": carry["B"],
                    "process_tag_name": carry["C"],
                    "sub_tag_name": carry["D"],
                    "endpoint": endpoint,
                }
            )
    return parsed


def build_alignment_report(api_records: list[dict[str, Any]], rule_bundle: dict[str, Any]) -> dict[str, Any]:
    api_business_categories = sorted({normalize_text(item["business_category"]) for item in api_records if normalize_text(item["business_category"])})
    api_business_subcategories = sorted({normalize_text(item["business_subcategory"]) for item in api_records if normalize_text(item["business_subcategory"])})
    api_process_tags = sorted({normalize_text(item["process_tag_name"]) for item in api_records if normalize_text(item["process_tag_name"])})
    api_sub_tags = sorted({normalize_text(item["sub_tag_name"]) for item in api_records if normalize_text(item["sub_tag_name"])})

    rule_categories = sorted({normalize_text(item["name"]) for item in rule_bundle.get("categories", []) if normalize_text(item["name"])})
    rule_points = sorted({normalize_text(item["review_point"]) for item in rule_bundle.get("rules", []) if normalize_text(item["review_point"])})

    api_lookup = {normalize_lookup_key(item) for item in [*api_process_tags, *api_sub_tags]}
    missing_rule_points = [point for point in rule_points if normalize_lookup_key(point) not in api_lookup]

    aliasable_rule_points = [
        {"rule_point": point, "suggested_api_tag": REVIEW_POINT_ALIAS_SUGGESTIONS.get(point, "")}
        for point in missing_rule_points
        if point in REVIEW_POINT_ALIAS_SUGGESTIONS
    ]

    missing_rule_categories = [category for category in rule_categories if normalize_lookup_key(category) not in {normalize_lookup_key(item) for item in api_business_subcategories}]
    aliasable_rule_categories = [
        {"rule_category": category, "suggested_api_subcategory": ""}
        for category in missing_rule_categories
        if category in CATEGORY_ALIAS_SUGGESTIONS.values()
    ]

    api_only_subcategories = [
        category
        for category in api_business_subcategories
        if normalize_lookup_key(category) not in {normalize_lookup_key(item) for item in rule_categories}
    ]

    aliasable_api_subcategories = [
        {"api_subcategory": item, "suggested_rule_category": CATEGORY_ALIAS_SUGGESTIONS[item]}
        for item in api_only_subcategories
        if item in CATEGORY_ALIAS_SUGGESTIONS
    ]

    return {
        "summary": {
            "api_record_count": len(api_records),
            "api_business_category_count": len(api_business_categories),
            "api_business_subcategory_count": len(api_business_subcategories),
            "api_process_tag_count": len(api_process_tags),
            "api_sub_tag_count": len(api_sub_tags),
            "rule_count": int(rule_bundle.get("summary", {}).get("rule_count") or 0),
            "rule_category_count": len(rule_categories),
            "rule_point_count": len(rule_points),
        },
        "api_dimensions": {
            "business_categories": api_business_categories,
            "business_subcategories": api_business_subcategories,
            "process_tags": api_process_tags,
            "sub_tags": api_sub_tags,
        },
        "rule_dimensions": {
            "categories": rule_categories,
            "review_points": rule_points,
        },
        "mismatch": {
            "rule_points_not_covered_by_api_tags": missing_rule_points,
            "rule_categories_not_covered_by_api_subcategories": missing_rule_categories,
            "api_subcategories_not_covered_by_rule_categories": api_only_subcategories,
        },
        "alias_suggestions": {
            "category_aliases": CATEGORY_ALIAS_SUGGESTIONS,
            "review_point_aliases": REVIEW_POINT_ALIAS_SUGGESTIONS,
            "aliasable_rule_points": aliasable_rule_points,
            "aliasable_api_subcategories": aliasable_api_subcategories,
            "aliasable_rule_categories": aliasable_rule_categories,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check alignment between API-tag matrix and review rules.")
    parser.add_argument("--api-xlsx", default="", help="Path to 620标签配置 xlsx.")
    parser.add_argument("--rule-xlsx", default="", help="Path to 立项大模型评审规则说明 xlsx.")
    parser.add_argument(
        "--output",
        default=str(repo_root() / "runtime" / "api_rule_alignment_260316.json"),
        help="Path for output JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_path = resolve_620_path(args.api_xlsx or None)
    rule_path = resolve_rule_path(args.rule_xlsx or None)
    api_records = parse_620_records(api_path)
    rule_bundle = parse_rule_bundle(rule_path)
    report = build_alignment_report(api_records, rule_bundle)
    payload = {
        "source": {"api_xlsx": str(api_path), "rule_xlsx": str(rule_path)},
        "report": report,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Alignment report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
