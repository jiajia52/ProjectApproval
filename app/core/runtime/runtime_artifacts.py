from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from app.core.config.paths import (
    ACCEPTANCE_RULES_BUNDLE_PATH,
    ACCEPTANCE_SKILL_MANIFEST_PATH,
    ACCEPTANCE_SKILLS_DIR,
    CONFIG_PATH,
    INITIATION_SKILLS_DIR,
    LEGACY_SKILL_MANIFEST_PATH,
    PROJECT_ROOT,
    RULES_BUNDLE_PATH,
    SCRIPTS_DIR,
    SKILL_MANIFEST_PATH,
    TASK_ORDER_RULES_BUNDLE_PATH,
    TASK_ORDER_SKILL_MANIFEST_PATH,
    TASK_ORDER_SKILLS_DIR,
    find_acceptance_rule_matrix_path,
    find_rule_matrix_path,
    find_task_order_rule_matrix_path,
    scene_skills_dir,
)
from app.core.config.scenes import normalize_scene
from app.skills.manager import get_skill_manager

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_project_approval_bundle import build_project_bundle, load_or_create_config, resolve_rule_matrix_path  # noqa: E402
from extract_review_rules import parse_rule_bundle, write_json  # noqa: E402
from generate_approval_item_skills import generate_approval_item_skills  # noqa: E402

SCENE_INITIATION = "initiation"
SCENE_ACCEPTANCE = "acceptance"
SCENE_TASK_ORDER = "task_order"


def should_rebuild_bundle(rule_matrix_path: Path) -> bool:
    return not RULES_BUNDLE_PATH.exists() or RULES_BUNDLE_PATH.stat().st_mtime < rule_matrix_path.stat().st_mtime


def should_regenerate_skills(
    rule_matrix_path: Path,
    *,
    manifest_path: Path,
    skills_dir: Path,
) -> bool:
    if not manifest_path.exists():
        return True
    if manifest_path.stat().st_mtime < rule_matrix_path.stat().st_mtime:
        return True
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return True
    expected_root = skills_dir.resolve()
    for skill in payload.get("skills", []):
        directory_raw = str(skill.get("directory", "")).strip()
        if not directory_raw:
            return True
        directory = Path(directory_raw).resolve()
        if directory != expected_root and expected_root not in directory.parents:
            return True
        if not directory.exists():
            return True
    return False


def migrate_legacy_initiation_skills() -> None:
    INITIATION_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for legacy_dir in sorted(scene_skills_dir(SCENE_INITIATION).parent.glob("approval-*")):
        if not legacy_dir.is_dir():
            continue
        target_dir = INITIATION_SKILLS_DIR / legacy_dir.name
        if target_dir.exists():
            continue
        shutil.move(str(legacy_dir), str(target_dir))
    if LEGACY_SKILL_MANIFEST_PATH.exists() and not SKILL_MANIFEST_PATH.exists():
        SKILL_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_SKILL_MANIFEST_PATH, SKILL_MANIFEST_PATH)


def normalize_runtime_generation_paths(config: dict[str, Any]) -> dict[str, Any]:
    generation = config.setdefault("generation", {})
    output_dir = Path(str(generation.get("output_dir", "runtime") or "runtime")).as_posix().rstrip("/")
    rules_output = Path(str(generation.get("rules_output", "runtime/review_rules.json") or "runtime/review_rules.json")).as_posix()
    changed = False
    if output_dir in {"runtime", ".", ""}:
        generation["output_dir"] = "runtime/initiation"
        changed = True
    if rules_output in {"review_rules.json", "runtime/review_rules.json"}:
        generation["rules_output"] = "runtime/initiation/review_rules.json"
        changed = True
    if changed:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def ensure_runtime_artifacts(*, force: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    migrate_legacy_initiation_skills()
    rule_matrix_path = find_rule_matrix_path()
    bootstrap_rules = parse_rule_bundle(rule_matrix_path)
    config = load_or_create_config(CONFIG_PATH, PROJECT_ROOT, bootstrap_rules)
    config = normalize_runtime_generation_paths(config)
    rule_source_path = resolve_rule_matrix_path(PROJECT_ROOT, config)
    rules_bundle = parse_rule_bundle(rule_source_path)

    if force or should_rebuild_bundle(rule_source_path):
        build_project_bundle(root=PROJECT_ROOT, config_path=CONFIG_PATH)
        rules_bundle = parse_rule_bundle(rule_source_path)

    if force or should_regenerate_skills(
        rule_source_path,
        manifest_path=SKILL_MANIFEST_PATH,
        skills_dir=INITIATION_SKILLS_DIR,
    ):
        enabled_skill_groups = set(config.get("generation", {}).get("enabled_skill_groups", []))
        generate_approval_item_skills(
            rules_bundle,
            output_dir=INITIATION_SKILLS_DIR,
            enabled_review_points=enabled_skill_groups or None,
        )

    get_skill_manager(SCENE_INITIATION).initialize()
    return config, rules_bundle


def ensure_acceptance_artifacts(*, force: bool = False) -> dict[str, Any]:
    rule_source_path = find_acceptance_rule_matrix_path()
    rules_bundle = parse_rule_bundle(rule_source_path)

    if force or not ACCEPTANCE_RULES_BUNDLE_PATH.exists() or (
        ACCEPTANCE_RULES_BUNDLE_PATH.stat().st_mtime < rule_source_path.stat().st_mtime
    ):
        write_json(ACCEPTANCE_RULES_BUNDLE_PATH, rules_bundle)

    if force or should_regenerate_skills(
        rule_source_path,
        manifest_path=ACCEPTANCE_SKILL_MANIFEST_PATH,
        skills_dir=ACCEPTANCE_SKILLS_DIR,
    ):
        generate_approval_item_skills(
            rules_bundle,
            output_dir=ACCEPTANCE_SKILLS_DIR,
        )

    get_skill_manager(SCENE_ACCEPTANCE).initialize()
    return rules_bundle


def ensure_task_order_artifacts(*, force: bool = False) -> dict[str, Any]:
    rule_source_path = find_task_order_rule_matrix_path()
    rules_bundle = parse_rule_bundle(rule_source_path)

    if force or not TASK_ORDER_RULES_BUNDLE_PATH.exists() or (
        TASK_ORDER_RULES_BUNDLE_PATH.stat().st_mtime < rule_source_path.stat().st_mtime
    ):
        write_json(TASK_ORDER_RULES_BUNDLE_PATH, rules_bundle)

    if force or should_regenerate_skills(
        rule_source_path,
        manifest_path=TASK_ORDER_SKILL_MANIFEST_PATH,
        skills_dir=TASK_ORDER_SKILLS_DIR,
    ):
        generate_approval_item_skills(
            rules_bundle,
            output_dir=TASK_ORDER_SKILLS_DIR,
        )

    get_skill_manager(SCENE_TASK_ORDER).initialize()
    return rules_bundle


def ensure_scene_artifacts(scene: str = SCENE_INITIATION, *, force: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_scene = _normalize_skill_scene(scene)
    if normalized_scene == SCENE_TASK_ORDER:
        return {}, ensure_task_order_artifacts(force=force)
    if normalized_scene == SCENE_ACCEPTANCE:
        return {}, ensure_acceptance_artifacts(force=force)
    return ensure_runtime_artifacts(force=force)


def _normalize_skill_scene(scene: str | None) -> str:
    normalized = str(scene or "").strip().lower()
    if normalized in {SCENE_TASK_ORDER, "task-order", "taskorder"}:
        return SCENE_TASK_ORDER
    return normalize_scene(scene)
