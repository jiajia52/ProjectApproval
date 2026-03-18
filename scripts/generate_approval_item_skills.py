#!/usr/bin/env python3
"""Generate approval skills grouped by process tab."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from extract_review_rules import default_xlsx_path, parse_rule_bundle


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_rules_path(root: Path | None = None) -> Path:
    active_root = root or repo_root()
    return active_root / "runtime" / "review_rules.json"


def default_output_dir(root: Path | None = None) -> Path:
    active_root = root or repo_root()
    return active_root / "skills"


def slugify(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-")
    return text[:80] or "skill"


def unique_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = (value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def build_skill_id(tab: str) -> str:
    return f"approval-{slugify(tab)}".lower()


def collect_skill_groups(
    rules_bundle: dict[str, Any],
    *,
    enabled_review_points: set[str] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: list[str] = []

    for rule in rules_bundle["rules"]:
        tab = (rule.get("tab") or "").strip()
        review_point = (rule.get("review_point") or "").strip()
        if not tab:
            continue
        if enabled_review_points and tab not in enabled_review_points and review_point not in enabled_review_points:
            continue
        if tab not in grouped:
            order.append(tab)
        grouped[tab].append(rule)

    groups: list[dict[str, Any]] = []
    for tab in order:
        rules = grouped[tab]
        categories = unique_list(
            [item.get("category", "") for rule in rules for item in rule.get("applicable_categories", [])]
        )
        group_names = unique_list(
            [item.get("group", "") for rule in rules for item in rule.get("applicable_categories", [])]
        )
        review_points = unique_list([rule.get("review_point", "") for rule in rules])
        review_contents = unique_list([rule.get("review_content", "") for rule in rules])
        model_dimensions = unique_list([rule.get("model_dimension", "") for rule in rules])
        dimensions = unique_list([rule.get("dimension", "") for rule in rules])

        subrules = [
            {
                "rule_id": rule["rule_id"],
                "review_point": rule.get("review_point", ""),
                "review_content": rule.get("review_content", ""),
                "rule_text": rule.get("rule_text", ""),
                "categories": unique_list(
                    [item.get("category", "") for item in rule.get("applicable_categories", [])]
                ),
            }
            for rule in rules
        ]

        groups.append(
            {
                "skill_id": build_skill_id(tab),
                "skill_name": f"{build_skill_id(tab)}-{tab}",
                "tab": tab,
                "rule_count": len(rules),
                "rule_ids": [rule["rule_id"] for rule in rules],
                "review_points": review_points,
                "review_contents": review_contents,
                "categories": categories,
                "group_names": group_names,
                "tabs": [tab],
                "model_dimensions": model_dimensions,
                "dimensions": dimensions,
                "rules": subrules,
                "summary": f"{tab}，包含 {len(rules)} 条评审子规则。",
            }
        )
    return groups


def build_rules_frontmatter(group: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    for item in group["rules"]:
        summary = (item["rule_text"] or "按审批材料判断").splitlines()[0]
        rules.append(f"- {item['review_point']} / {item['review_content']}: {summary}")
    return rules


def build_grouped_rule_sections(group: dict[str, Any]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in group["rules"]:
        grouped[item["review_point"]].append(item)

    lines: list[str] = []
    for review_point in group["review_points"]:
        lines.append(f"### {review_point}")
        for item in grouped.get(review_point, []):
            content = item["review_content"] or "未命名内容"
            rule_text = item["rule_text"] or "该项在规则表中未填写具体规则，按“不需要/不适用”处理，不额外扩展否决条件。"
            categories = "、".join(item["categories"]) or "无明确适用品类"
            lines.append(f"- `{item['rule_id']}` {content}")
            lines.append(f"  规则: {rule_text}")
            lines.append(f"  适用品类: {categories}")
    return "\n".join(lines)


def build_skill_markdown(group: dict[str, Any], source_name: str) -> str:
    categories = "、".join(group["categories"]) or "全部品类"
    review_points = "、".join(group["review_points"]) or "-"
    dimensions = "、".join(group["dimensions"]) or "-"
    model_dimensions = "、".join(group["model_dimensions"]) or "-"
    grouped_rules = build_grouped_rule_sections(group)

    return "\n".join(
        [
            "---",
            f"skill_id: {group['skill_id']}",
            f"name: {group['skill_name']}",
            f"description: 项目立项审批规则，聚合“{group['tab']}”进程tab页下全部评审点。用于项目立项审批、远程项目审批和大模型审批建议生成时，对该tab页相关内容进行统一复核。",
            "project_type: ALL",
            "task_type: PROJECT_APPROVAL",
            "object_type: PROJECT_TAB",
            "spec_ids:",
            f"- builtin:{source_name}",
            "rules:",
            *build_rules_frontmatter(group),
            "enabled: true",
            "---",
            f"# Skill: {group['skill_name']}",
            "",
            "## 适用范围",
            f"- 进程tab页：{group['tab']}",
            f"- 规则数量：{group['rule_count']}",
            f"- 模型维度：{model_dimensions}",
            f"- 业务维度：{dimensions}",
            f"- 涵盖评审点：{review_points}",
            f"- 适用品类：{categories}",
            "",
            "## 规则依据",
            f"- {source_name}",
            "",
            "## 审批目标",
            f"- 对“{group['tab']}”tab页下的全部评审点、评审内容和规则进行一次性复核。",
            "- 只基于该tab对应的材料、接口数据和映射后的项目文档做判断。",
            "- 不跨tab扩展结论；跨tab要求只能作为提示，不能作为当前skill的否决依据。",
            "",
            "## 结构化规则",
            grouped_rules,
            "",
            "## 审批口径（强制）",
            "- 必须逐条覆盖本Skill下全部规则，不得跳项；不适用项标记为 N/A，并给出基于材料的理由。",
            "- 若规则文本为空，按“不需要/规则表未要求”处理，不得自行补充新的强制否决条件。",
            "- 优先使用远程接口原始返回、映射后的项目文档和审批落盘文件作为证据。",
            "- 输出只保留复核后的结论、问题、建议，不输出思维链或内部推理过程。",
            "- 当前Skill只负责本tab页，不替代其他7个tab的审查职责。",
            "",
            "## 输出要求",
            "- 输出 JSON 对象，至少包含 `review_point`、`status`、`summary`、`item_results`、`evidence`、`suggestion`。",
            f"- `review_point` 固定输出 `{group['tab']}`。",
            "- `item_results` 必须覆盖本Skill中列出的全部规则项。",
            "",
        ]
    )


def build_openai_yaml(group: dict[str, Any]) -> str:
    return "\n".join(
        [
            "interface:",
            f'  display_name: "{group["tab"]}"',
            f'  short_description: "立项审批tab技能：{group["tab"]}"',
            '  default_prompt: "Use this skill to review all approval rules grouped under the project process tab."',
            "",
        ]
    )


def clear_generated_skills(output_dir: Path) -> None:
    for candidate in output_dir.glob("approval-*"):
        if candidate.is_dir():
            shutil.rmtree(candidate)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()


def generate_approval_item_skills(
    rules_bundle: dict[str, Any],
    output_dir: Path | None = None,
    *,
    enabled_review_points: set[str] | None = None,
    clean: bool = True,
) -> dict[str, Any]:
    active_output_dir = output_dir or default_output_dir()
    active_output_dir.mkdir(parents=True, exist_ok=True)
    if clean:
        clear_generated_skills(active_output_dir)

    source_name = Path(str(rules_bundle.get("source") or default_xlsx_path())).name
    groups = collect_skill_groups(rules_bundle, enabled_review_points=enabled_review_points)
    manifest: list[dict[str, Any]] = []
    for group in groups:
        skill_dir = active_output_dir / group["skill_id"]
        agents_dir = skill_dir / "agents"
        skill_dir.mkdir(parents=True, exist_ok=True)
        agents_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(build_skill_markdown(group, source_name), encoding="utf-8")
        (agents_dir / "openai.yaml").write_text(build_openai_yaml(group), encoding="utf-8")
        metadata = {
            "skill_id": group["skill_id"],
            "skill_name": group["skill_name"],
            "directory": str(skill_dir),
            "review_point": group["tab"],
            "tab": group["tab"],
            "rule_count": group["rule_count"],
            "rule_ids": group["rule_ids"],
            "review_points": group["review_points"],
            "review_contents": group["review_contents"],
            "categories": group["categories"],
            "group_names": group["group_names"],
            "tabs": group["tabs"],
            "model_dimensions": group["model_dimensions"],
            "dimensions": group["dimensions"],
            "summary": group["summary"],
            "rules": group["rules"],
        }
        (skill_dir / "skill.metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest.append(metadata)

    payload = {
        "generated_count": len(manifest),
        "grouping_key": "tab",
        "output_dir": str(active_output_dir),
        "skills": manifest,
    }
    (active_output_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate grouped approval skills by process tab.")
    parser.add_argument("--rules", default=str(default_rules_path()), help="Path to review_rules.json.")
    parser.add_argument("--output-dir", default=str(default_output_dir()), help="Directory for generated approval skills.")
    parser.add_argument("--xlsx", default="", help="Optional xlsx path if rules json does not exist.")
    parser.add_argument(
        "--review-point",
        action="append",
        dest="review_points",
        default=[],
        help="Only generate the specified review point or tab. Can be repeated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rules_path = Path(args.rules)
    if rules_path.exists():
        rules_bundle = json.loads(rules_path.read_text(encoding="utf-8"))
    else:
        xlsx_path = Path(args.xlsx) if args.xlsx else default_xlsx_path()
        rules_bundle = parse_rule_bundle(xlsx_path)
    enabled_review_points = set(args.review_points) if args.review_points else None
    result = generate_approval_item_skills(
        rules_bundle,
        Path(args.output_dir),
        enabled_review_points=enabled_review_points,
    )
    print(
        json.dumps(
            {
                "generated_count": result["generated_count"],
                "grouping_key": result["grouping_key"],
                "output_dir": result["output_dir"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
