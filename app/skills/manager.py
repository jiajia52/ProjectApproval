"""Register and inspect local approval-item skills through AgentScope."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from agentscope import init
from agentscope.tool import Toolkit

from app.core.paths import PROJECT_ROOT, SKILLS_DIR


class AgentScopeSkillManager:
    """Register root-level approval item skills."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or PROJECT_ROOT).resolve()
        self.skills_dir = SKILLS_DIR
        self.toolkit = Toolkit()
        self._initialized = False
        self._registered_paths: set[str] = set()

    def initialize(self) -> None:
        if self._initialized:
            return
        init(project="project-approval", name="skill-manager", logging_level="INFO")
        self._initialized = True
        for candidate in sorted(self.skills_dir.glob("*")):
            if candidate.is_dir() and (candidate / "SKILL.md").exists():
                self._register_skill_dir(candidate)

    def _register_skill_dir(self, directory: Path) -> None:
        directory_str = str(directory)
        if directory_str in self._registered_paths:
            return
        self.toolkit.register_agent_skill(directory_str)
        self._registered_paths.add(directory_str)

    def list_skills(self) -> list[dict[str, Any]]:
        manifest_path = self.skills_dir / "manifest.json"
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return [
                {
                    "name": item.get("skill_name", ""),
                    "description": item.get("summary", ""),
                    "directory": item.get("directory", ""),
                    "review_point": item.get("review_point", ""),
                    "rule_count": item.get("rule_count", 0),
                    "review_contents": item.get("review_contents", []),
                    "categories": item.get("categories", []),
                }
                for item in payload.get("skills", [])
            ]

        self.initialize()
        skills: list[dict[str, Any]] = []
        for skill in self.toolkit.skills.values():
            if isinstance(skill, dict):
                skills.append(
                    {
                        "name": skill.get("name", ""),
                        "description": skill.get("description", ""),
                        "directory": skill.get("dir", ""),
                    }
                )
                continue
            skills.append(
                {
                    "name": getattr(skill, "name", ""),
                    "description": getattr(skill, "description", ""),
                    "directory": getattr(skill, "dir", ""),
                }
            )
        return skills

    def list_skill_files(self) -> list[dict[str, Any]]:
        manifest_path = self.skills_dir / "manifest.json"
        items: list[dict[str, Any]] = []
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            for item in payload.get("skills", []):
                directory = Path(str(item.get("directory") or "")).resolve()
                if not directory.exists():
                    continue
                skill_file = directory / "SKILL.md"
                if not skill_file.exists():
                    continue
                items.append(
                    {
                        "skill_id": item.get("skill_id") or directory.name,
                        "skill_name": item.get("skill_name") or directory.name,
                        "review_point": item.get("review_point") or "",
                        "directory": str(directory),
                        "path": str(skill_file),
                        "relative_path": str(skill_file.relative_to(self.root)).replace("\\", "/"),
                        "modified_at": skill_file.stat().st_mtime,
                    }
                )
            return items

        for directory in sorted(self.skills_dir.glob("approval-*")):
            skill_file = directory / "SKILL.md"
            if not skill_file.exists():
                continue
            items.append(
                {
                    "skill_id": directory.name,
                    "skill_name": directory.name,
                    "review_point": directory.name.replace("approval-", ""),
                    "directory": str(directory.resolve()),
                    "path": str(skill_file.resolve()),
                    "relative_path": str(skill_file.relative_to(self.root)).replace("\\", "/"),
                    "modified_at": skill_file.stat().st_mtime,
                }
            )
        return items

    def _resolve_skill_file(self, skill_id: str) -> Path:
        normalized = str(skill_id or "").strip()
        if not normalized:
            raise FileNotFoundError("Missing skill id.")
        for item in self.list_skill_files():
            if item["skill_id"] == normalized:
                path = Path(item["path"]).resolve()
                if self.skills_dir.resolve() not in path.parents:
                    raise FileNotFoundError("Invalid skill file path.")
                return path
        raise FileNotFoundError(f"Skill not found: {normalized}")

    def read_skill_file(self, skill_id: str) -> dict[str, Any]:
        path = self._resolve_skill_file(skill_id)
        return {
            "skill_id": skill_id,
            "path": str(path),
            "relative_path": str(path.relative_to(self.root)).replace("\\", "/"),
            "content": path.read_text(encoding="utf-8"),
        }

    def save_skill_file(self, skill_id: str, content: str) -> dict[str, Any]:
        path = self._resolve_skill_file(skill_id)
        path.write_text(str(content), encoding="utf-8")
        return {
            "skill_id": skill_id,
            "path": str(path),
            "relative_path": str(path.relative_to(self.root)).replace("\\", "/"),
            "modified_at": path.stat().st_mtime,
        }


_MANAGER: AgentScopeSkillManager | None = None


def get_skill_manager() -> AgentScopeSkillManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = AgentScopeSkillManager()
    return _MANAGER
