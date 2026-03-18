from __future__ import annotations

from pathlib import Path

from app.core import env as _env  # noqa: F401

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
RUNTIME_DIR = PROJECT_ROOT / "runtime"
CONFIG_DIR = RUNTIME_DIR / "config"
LOG_DIR = RUNTIME_DIR / "logs"
LEGACY_FRONTEND_DIR = resolve_resource_path("app", "frontend")
FRONTEND_SOURCE_DIR = resolve_resource_path("frontend")
FRONTEND_DIR = resolve_resource_path("frontend", "dist")
SKILLS_DIR = resolve_resource_path("skills")
SCRIPTS_DIR = resolve_resource_path("scripts")

GENERATED_DIR = RUNTIME_DIR
APPROVAL_ITEM_SKILLS_DIR = SKILLS_DIR
APPROVAL_RUNS_DIR = RUNTIME_DIR / "approval_runs"
API_DUMPS_DIR = RUNTIME_DIR / "api_dumps"
API_RESULT_DIR = RUNTIME_DIR / "api_result"
PROJECT_DOCUMENTS_DIR = RUNTIME_DIR / "project_documents"
REVIEW_FEEDBACK_DIR = RUNTIME_DIR / "review_feedback"
STARTUP_CHECKS_PATH = RUNTIME_DIR / "startup_checks.json"

CONFIG_PATH = CONFIG_DIR / "skill_config.json"
INTEGRATION_CONFIG_PATH = CONFIG_DIR / "integration_config.json"
SAMPLE_INPUT_PATH = DATA_DIR / "approval_input.sample.json"
RULES_BUNDLE_PATH = GENERATED_DIR / "review_rules.json"
SKILL_MANIFEST_PATH = APPROVAL_ITEM_SKILLS_DIR / "manifest.json"


def find_rule_matrix_path() -> Path:
    matches = [
        path
        for path in DATA_DIR.glob("*.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    ]
    if not matches:
        raise FileNotFoundError("No .xlsx rule matrix found in data/.")

    preferred = [
        path
        for path in matches
        if "立项大模型评审规则说明" in path.name and "620标签配置" not in path.name
    ]
    if not preferred:
        preferred = [path for path in matches if "评审规则说明" in path.name and "620标签配置" not in path.name]
    candidates = preferred or [path for path in matches if "620标签配置" not in path.name] or matches
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))
