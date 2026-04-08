from __future__ import annotations

from typing import Any

from app.approvals.review.category_aliases import CATEGORY_NAME_ALIASES, canonical_category_name
from app.core.runtime.runtime_artifacts import ensure_scene_artifacts

SCENE_INITIATION = "initiation"


def normalize_category_key(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(character for character in text if character.isalnum())


def known_category_lookup(scene: str = SCENE_INITIATION) -> dict[str, str]:
    _, rules_bundle = ensure_scene_artifacts(scene, force=False)
    lookup = {
        normalize_category_key(item.get("name")): str(item.get("name"))
        for item in rules_bundle.get("categories", [])
        if str(item.get("name") or "").strip()
    }
    for alias, target in CATEGORY_NAME_ALIASES.items():
        canonical_key = normalize_category_key(target)
        if canonical_key in lookup:
            lookup[normalize_category_key(alias)] = lookup[canonical_key]
    return lookup


def resolve_project_category_name(
    requested_category: str | None = None,
    summary: dict[str, Any] | None = None,
    document: dict[str, Any] | None = None,
    scene: str = SCENE_INITIATION,
    default_project_category: str = "",
) -> str:
    category_lookup = known_category_lookup(scene=scene)
    if not category_lookup:
        fallback = canonical_category_name(requested_category or default_project_category)
        return str(fallback or default_project_category).strip() or default_project_category

    summary_candidates: list[Any] = []
    if isinstance(summary, dict):
        summary_candidates.extend(
            [
                summary.get("business_subcategory_name"),
                summary.get("businessSubcategoryName"),
                summary.get("projectClassifyName"),
                summary.get("project_category_name"),
                summary.get("projectCategoryName"),
                summary.get("project_type_name"),
                summary.get("projectTypeName"),
            ]
        )
    if isinstance(document, dict):
        document_summary = document.get("project_summary")
        if isinstance(document_summary, dict):
            summary_candidates.extend(
                [
                    document_summary.get("business_subcategory_name"),
                    document_summary.get("project_category_name"),
                    document_summary.get("project_type_name"),
                ]
            )

    for candidate in summary_candidates:
        normalized = normalize_category_key(canonical_category_name(candidate))
        if normalized and normalized in category_lookup:
            return category_lookup[normalized]

    requested_normalized = normalize_category_key(canonical_category_name(requested_category))
    if requested_normalized and requested_normalized in category_lookup:
        return category_lookup[requested_normalized]
    return category_lookup.get(
        normalize_category_key(default_project_category),
        next(iter(category_lookup.values()), default_project_category),
    )
