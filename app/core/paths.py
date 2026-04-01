from __future__ import annotations

from pathlib import Path

from app.core import env as _env  # noqa: F401
from app.core.scenes import SCENE_ACCEPTANCE, SCENE_INITIATION, SCENE_TASK_ORDER, normalize_scene

PROJECT_ROOT = _env.PROJECT_ROOT
BUNDLE_ROOT = _env.BUNDLE_ROOT
SOURCE_ROOT = _env.SOURCE_ROOT


def resolve_resource_path(*parts: str) -> Path:
    relative_path = Path(*parts)
    for root in [PROJECT_ROOT, BUNDLE_ROOT, SOURCE_ROOT]:
        candidate = (root / relative_path).resolve()
        if candidate.exists():
            return candidate
    return (PROJECT_ROOT / relative_path).resolve()


APP_DIR = resolve_resource_path("app")
DATA_DIR = resolve_resource_path("data")
MATERIALS_DIR = resolve_resource_path("materials")
INITIATION_MATERIALS_DIR = resolve_resource_path("materials", "initiation")
INITIATION_INTERFACES_DIR = resolve_resource_path("materials", "initiation", "interfaces")
INITIATION_RULES_DIR = resolve_resource_path("materials", "initiation", "rules")
INITIATION_SAMPLES_DIR = resolve_resource_path("materials", "initiation", "samples")
ACCEPTANCE_MATERIALS_DIR = resolve_resource_path("materials", "acceptance")
ACCEPTANCE_RULES_DIR = resolve_resource_path("materials", "acceptance", "rules")
TASK_ORDER_MATERIALS_DIR = resolve_resource_path("materials", "task_order")
TASK_ORDER_RULES_DIR = resolve_resource_path("materials", "task_order", "rules")
RUNTIME_DIR = PROJECT_ROOT / "runtime"
CONFIG_DIR = RUNTIME_DIR / "config"
FRONTEND_DIR = resolve_resource_path("frontend", "dist")
SKILLS_DIR = resolve_resource_path("skills")
SCRIPTS_DIR = resolve_resource_path("scripts")

LEGACY_LOG_DIR = RUNTIME_DIR / "logs"
LEGACY_GENERATED_DIR = RUNTIME_DIR
LEGACY_APPROVAL_RUNS_DIR = RUNTIME_DIR / "approval_runs"
API_DUMPS_DIR = RUNTIME_DIR / "api_dumps"
LEGACY_API_RESULT_DIR = RUNTIME_DIR / "api_result"
LEGACY_PROJECT_DOCUMENTS_DIR = RUNTIME_DIR / "project_documents"
LEGACY_REVIEW_FEEDBACK_DIR = RUNTIME_DIR / "review_feedback"
STARTUP_CHECKS_PATH = RUNTIME_DIR / "startup_checks.json"

INITIATION_RUNTIME_DIR = RUNTIME_DIR / SCENE_INITIATION
ACCEPTANCE_RUNTIME_DIR = RUNTIME_DIR / SCENE_ACCEPTANCE
TASK_ORDER_RUNTIME_DIR = RUNTIME_DIR / SCENE_TASK_ORDER
LOG_DIR = INITIATION_RUNTIME_DIR / "logs"
ACCEPTANCE_LOG_DIR = ACCEPTANCE_RUNTIME_DIR / "logs"
TASK_ORDER_LOG_DIR = TASK_ORDER_RUNTIME_DIR / "logs"
GENERATED_DIR = INITIATION_RUNTIME_DIR
ACCEPTANCE_GENERATED_DIR = ACCEPTANCE_RUNTIME_DIR
TASK_ORDER_GENERATED_DIR = TASK_ORDER_RUNTIME_DIR
API_RESULT_DIR = INITIATION_RUNTIME_DIR / "api_result"
ACCEPTANCE_API_RESULT_DIR = ACCEPTANCE_RUNTIME_DIR / "api_result"
TASK_ORDER_API_RESULT_DIR = TASK_ORDER_RUNTIME_DIR / "api_result"
PROJECT_DOCUMENTS_DIR = INITIATION_RUNTIME_DIR / "project_documents"
ACCEPTANCE_PROJECT_DOCUMENTS_DIR = ACCEPTANCE_RUNTIME_DIR / "project_documents"
TASK_ORDER_PROJECT_DOCUMENTS_DIR = TASK_ORDER_RUNTIME_DIR / "project_documents"
REVIEW_FEEDBACK_DIR = INITIATION_RUNTIME_DIR / "review_feedback"
ACCEPTANCE_REVIEW_FEEDBACK_DIR = ACCEPTANCE_RUNTIME_DIR / "review_feedback"
TASK_ORDER_REVIEW_FEEDBACK_DIR = TASK_ORDER_RUNTIME_DIR / "review_feedback"
APPROVAL_RUNS_DIR = INITIATION_RUNTIME_DIR / "approval_runs"
ACCEPTANCE_APPROVAL_RUNS_DIR = ACCEPTANCE_RUNTIME_DIR / "approval_runs"
TASK_ORDER_APPROVAL_RUNS_DIR = TASK_ORDER_RUNTIME_DIR / "approval_runs"
INITIATION_SKILLS_DIR = SKILLS_DIR / SCENE_INITIATION
APPROVAL_ITEM_SKILLS_DIR = INITIATION_SKILLS_DIR
ACCEPTANCE_SKILLS_DIR = SKILLS_DIR / SCENE_ACCEPTANCE
TASK_ORDER_SKILLS_DIR = SKILLS_DIR / SCENE_TASK_ORDER

CONFIG_PATH = CONFIG_DIR / "skill_config.json"
INTEGRATION_CONFIG_PATH = CONFIG_DIR / "integration_config.json"
RULES_BUNDLE_PATH = GENERATED_DIR / "review_rules.json"
SKILL_MANIFEST_PATH = APPROVAL_ITEM_SKILLS_DIR / "manifest.json"
ACCEPTANCE_RULES_BUNDLE_PATH = ACCEPTANCE_GENERATED_DIR / "review_rules.json"
ACCEPTANCE_SKILL_MANIFEST_PATH = ACCEPTANCE_SKILLS_DIR / "manifest.json"
TASK_ORDER_RULES_BUNDLE_PATH = TASK_ORDER_GENERATED_DIR / "review_rules.json"
TASK_ORDER_SKILL_MANIFEST_PATH = TASK_ORDER_SKILLS_DIR / "manifest.json"
PROJECT_BUNDLE_PATH = GENERATED_DIR / "project_approval_project.json"
LATEST_APPROVAL_RESULT_PATH = GENERATED_DIR / "latest_approval_result.json"
ACCEPTANCE_LATEST_APPROVAL_RESULT_PATH = ACCEPTANCE_GENERATED_DIR / "latest_approval_result.json"
TASK_ORDER_LATEST_APPROVAL_RESULT_PATH = TASK_ORDER_GENERATED_DIR / "latest_approval_result.json"
LEGACY_RULES_BUNDLE_PATH = LEGACY_GENERATED_DIR / "review_rules.json"
LEGACY_ACCEPTANCE_RULES_BUNDLE_PATH = LEGACY_GENERATED_DIR / "acceptance_review_rules.json"
LEGACY_PROJECT_BUNDLE_PATH = LEGACY_GENERATED_DIR / "project_approval_project.json"
LEGACY_LATEST_APPROVAL_RESULT_PATH = LEGACY_GENERATED_DIR / "latest_approval_result.json"
LEGACY_SKILL_MANIFEST_PATH = SKILLS_DIR / "manifest.json"


def scene_runtime_dir(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_RUNTIME_DIR
    return ACCEPTANCE_RUNTIME_DIR if normalized == SCENE_ACCEPTANCE else INITIATION_RUNTIME_DIR


def scene_log_dir(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_LOG_DIR
    return ACCEPTANCE_LOG_DIR if normalized == SCENE_ACCEPTANCE else LOG_DIR


def scene_generated_dir(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_GENERATED_DIR
    return ACCEPTANCE_GENERATED_DIR if normalized == SCENE_ACCEPTANCE else GENERATED_DIR


def scene_api_result_dir(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_API_RESULT_DIR
    return ACCEPTANCE_API_RESULT_DIR if normalized == SCENE_ACCEPTANCE else API_RESULT_DIR


def scene_project_documents_dir(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_PROJECT_DOCUMENTS_DIR
    return ACCEPTANCE_PROJECT_DOCUMENTS_DIR if normalized == SCENE_ACCEPTANCE else PROJECT_DOCUMENTS_DIR


def scene_review_feedback_dir(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_REVIEW_FEEDBACK_DIR
    return ACCEPTANCE_REVIEW_FEEDBACK_DIR if normalized == SCENE_ACCEPTANCE else REVIEW_FEEDBACK_DIR


def scene_approval_runs_dir(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_APPROVAL_RUNS_DIR
    return ACCEPTANCE_APPROVAL_RUNS_DIR if normalized == SCENE_ACCEPTANCE else APPROVAL_RUNS_DIR


def scene_skills_dir(scene: str | None) -> Path:
    normalized = str(scene or "").strip().lower()
    if normalized in {SCENE_TASK_ORDER, "task-order", "taskorder"}:
        return TASK_ORDER_SKILLS_DIR
    return ACCEPTANCE_SKILLS_DIR if normalize_scene(scene) == SCENE_ACCEPTANCE else INITIATION_SKILLS_DIR


def scene_skill_manifest_path(scene: str | None) -> Path:
    normalized = str(scene or "").strip().lower()
    if normalized in {SCENE_TASK_ORDER, "task-order", "taskorder"}:
        return TASK_ORDER_SKILL_MANIFEST_PATH
    return ACCEPTANCE_SKILL_MANIFEST_PATH if normalize_scene(scene) == SCENE_ACCEPTANCE else SKILL_MANIFEST_PATH


def scene_rules_bundle_path(scene: str | None) -> Path:
    normalized = str(scene or "").strip().lower()
    if normalized in {SCENE_TASK_ORDER, "task-order", "taskorder"}:
        return TASK_ORDER_RULES_BUNDLE_PATH
    return ACCEPTANCE_RULES_BUNDLE_PATH if normalize_scene(scene) == SCENE_ACCEPTANCE else RULES_BUNDLE_PATH


def scene_latest_approval_result_path(scene: str | None) -> Path:
    normalized = normalize_scene(scene)
    if normalized == SCENE_TASK_ORDER:
        return TASK_ORDER_LATEST_APPROVAL_RESULT_PATH
    return ACCEPTANCE_LATEST_APPROVAL_RESULT_PATH if normalized == SCENE_ACCEPTANCE else LATEST_APPROVAL_RESULT_PATH


def resolve_existing_path(*candidate_parts: tuple[str, ...]) -> Path:
    for parts in candidate_parts:
        candidate = resolve_resource_path(*parts)
        if candidate.exists():
            return candidate
    return resolve_resource_path(*candidate_parts[0])


SAMPLE_INPUT_PATH = resolve_existing_path(
    ("materials", "initiation", "samples", "approval_input.sample.json"),
    ("data", "approval_input.sample.json"),
)


def _collect_xlsx(search_dirs: list[Path]) -> list[Path]:
    matches: list[Path] = []
    seen: set[Path] = set()
    for directory in search_dirs:
        for path in directory.glob("*.xlsx"):
            resolved = path.resolve()
            if resolved in seen or not path.is_file() or path.name.startswith("~$"):
                continue
            seen.add(resolved)
            matches.append(path)
    return matches


def _pick_latest(candidates: list[Path]) -> Path:
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_rule_matrix_path() -> Path:
    matches = _collect_xlsx([INITIATION_RULES_DIR, DATA_DIR])
    if not matches:
        raise FileNotFoundError("No .xlsx rule matrix found in materials/initiation/rules/ or data/.")

    non_620 = [path for path in matches if "620" not in path.name]
    candidates = non_620 or matches
    return _pick_latest(candidates)


def find_acceptance_rule_matrix_path() -> Path:
    matches = _collect_xlsx([ACCEPTANCE_RULES_DIR, DATA_DIR])
    if not matches:
        raise FileNotFoundError("No acceptance .xlsx rule matrix found in materials/acceptance/rules/ or data/.")

    non_interface = [path for path in matches if "接口" not in path.name]
    candidates = non_interface or matches
    return _pick_latest(candidates)


def find_task_order_rule_matrix_path() -> Path:
    matches = _collect_xlsx([TASK_ORDER_RULES_DIR, DATA_DIR])
    if not matches:
        raise FileNotFoundError("No task-order .xlsx rule matrix found in materials/task_order/rules/ or data/.")

    non_interface = [path for path in matches if "接口" not in path.name]
    candidates = non_interface or matches
    return _pick_latest(candidates)
