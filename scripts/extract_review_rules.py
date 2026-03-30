#!/usr/bin/env python3
"""Extract the project approval review matrix from the Excel source."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ACTIVE_MARKERS = {"\u221a", "Y", "y", "YES", "Yes", "1", "true", "True"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def rule_search_dirs() -> list[Path]:
    root = repo_root()
    return [
        root / "materials" / "initiation" / "rules",
        root / "data",
    ]


def default_xlsx_path() -> Path:
    matches: list[Path] = []
    seen: set[Path] = set()
    for directory in rule_search_dirs():
        for path in directory.glob("*.xlsx"):
            resolved = path.resolve()
            if resolved in seen or not path.is_file() or path.name.startswith("~$"):
                continue
            seen.add(resolved)
            matches.append(path)
    if not matches:
        raise FileNotFoundError("No .xlsx rule matrix found in materials/initiation/rules/ or data/.")

    preferred = [
        path
        for path in matches
        if "立项大模型评审规则说明" in path.name and "620标签配置" not in path.name
    ]
    if not preferred:
        preferred = [path for path in matches if "评审规则说明" in path.name and "620标签配置" not in path.name]
    candidates = preferred or [path for path in matches if "620标签配置" not in path.name] or matches
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def default_output_path() -> Path:
    return repo_root() / "runtime" / "initiation" / "review_rules.json"


def excel_col_to_index(column: str) -> int:
    index = 0
    for char in column:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index


def read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root:
        fragments: list[str] = []
        for node in item.iter(f"{{{SPREADSHEET_NS}}}t"):
            fragments.append(node.text or "")
        values.append("".join(fragments))
    return values


def read_sheet_rows(xlsx_path: Path, sheet_index: int = 0) -> tuple[str, list[dict[str, str]]]:
    with ZipFile(xlsx_path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relationships = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheets = workbook.find(f"{{{SPREADSHEET_NS}}}sheets")
        if sheets is None or len(sheets) <= sheet_index:
            raise ValueError(f"Sheet index {sheet_index} not found in {xlsx_path}.")

        sheet = sheets[sheet_index]
        sheet_name = sheet.attrib["name"]
        target = relationships[sheet.attrib[f"{{{REL_NS}}}id"]]
        shared = read_shared_strings(zf)

        worksheet = ET.fromstring(zf.read(f"xl/{target}"))
        sheet_data = worksheet.find(f"{{{SPREADSHEET_NS}}}sheetData")
        if sheet_data is None:
            return sheet_name, []

        rows: list[dict[str, str]] = []
        for row in sheet_data:
            row_data: dict[str, str] = {}
            for cell in row:
                cell_ref = cell.attrib.get("r", "")
                column = "".join(ch for ch in cell_ref if ch.isalpha())
                value_node = cell.find(f"{{{SPREADSHEET_NS}}}v")
                if not column or value_node is None:
                    continue
                value = value_node.text or ""
                if cell.attrib.get("t") == "s":
                    value = shared[int(value)]
                row_data[column] = value.strip()
            rows.append(row_data)
        return sheet_name, rows


def parse_rule_bundle(xlsx_path: Path) -> dict[str, Any]:
    if xlsx_path.name.startswith("~$"):
        raise ValueError(f"Refusing to read temporary Office lock file: {xlsx_path}")
    sheet_name, rows = read_sheet_rows(xlsx_path)
    if len(rows) < 3:
        raise ValueError("Rule matrix does not include the expected header rows.")

    group_header = rows[0]
    category_header = rows[1]
    category_columns = [
        column
        for column in sorted(category_header, key=excel_col_to_index)
        if excel_col_to_index(column) >= excel_col_to_index("H") and category_header.get(column, "")
    ]

    categories: list[dict[str, str]] = []
    current_group = ""
    for column in category_columns:
        group_name = group_header.get(column, "").strip()
        if group_name:
            current_group = group_name
        categories.append(
            {
                "column": column,
                "group": current_group or "unclassified",
                "name": category_header[column].strip(),
            }
        )

    carry_forward = {column: "" for column in ["A", "B", "C", "D", "E"]}
    rules: list[dict[str, Any]] = []
    category_counter: Counter[str] = Counter()
    tab_counter: Counter[str] = Counter()
    model_counter: Counter[str] = Counter()
    dimension_counter: Counter[str] = Counter()
    review_point_counter: Counter[str] = Counter()

    for row in rows[2:]:
        normalized: dict[str, str] = {}
        for column in ["A", "B", "C", "D", "E"]:
            value = row.get(column, "").strip()
            if value:
                carry_forward[column] = value
            normalized[column] = carry_forward[column]

        review_content = row.get("F", "").strip()
        rule_text = row.get("G", "").strip()
        if not any([normalized["B"], normalized["C"], normalized["D"], normalized["E"], review_content, rule_text]):
            continue
        if not review_content and not rule_text:
            continue

        applicable_categories: list[dict[str, str]] = []
        for category in categories:
            marker = row.get(category["column"], "").strip()
            if marker in ACTIVE_MARKERS:
                applicable_categories.append({"group": category["group"], "category": category["name"]})
                category_counter[category["name"]] += 1

        rule_record = {
            "rule_id": f"R{len(rules) + 1:03d}",
            "sequence": normalized["A"] or str(len(rules) + 1),
            "tab": normalized["B"],
            "model_dimension": normalized["C"],
            "dimension": normalized["D"],
            "review_point": normalized["E"],
            "review_content": review_content,
            "rule_text": rule_text,
            "applicable_categories": applicable_categories,
        }
        rules.append(rule_record)

        if rule_record["tab"]:
            tab_counter[rule_record["tab"]] += 1
        if rule_record["model_dimension"]:
            model_counter[rule_record["model_dimension"]] += 1
        if rule_record["dimension"]:
            dimension_counter[rule_record["dimension"]] += 1
        if rule_record["review_point"]:
            review_point_counter[rule_record["review_point"]] += 1

    return {
        "source": str(xlsx_path),
        "sheet": sheet_name,
        "categories": categories,
        "rules": rules,
        "summary": {
            "rule_count": len(rules),
            "category_count": len(categories),
            "by_tab": dict(sorted(tab_counter.items())),
            "by_model_dimension": dict(sorted(model_counter.items())),
            "by_dimension": dict(sorted(dimension_counter.items())),
            "by_review_point": dict(sorted(review_point_counter.items())),
            "by_category": dict(sorted(category_counter.items())),
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract review rules from the Excel matrix.")
    parser.add_argument("--xlsx", default=str(default_xlsx_path()), help="Path to the Excel rule matrix.")
    parser.add_argument("--output", default=str(default_output_path()), help="Path for the generated JSON rule bundle.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = parse_rule_bundle(Path(args.xlsx))
    write_json(Path(args.output), bundle)
    print(f"Extracted {bundle['summary']['rule_count']} rules to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
