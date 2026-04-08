from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from app.core.config.scenes import normalize_scene

SCENE_INITIATION = "initiation"
_ARCH_REVIEW_CACHE_LOCK = threading.Lock()
_ARCH_REVIEW_CACHE: dict[str, dict[str, Any]] = {}
_REVIEW_FEEDBACK_CACHE_LOCK = threading.Lock()
_REVIEW_FEEDBACK_CACHE: dict[str, dict[str, Any]] = {}


def architecture_review_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_ARCH_REVIEW_CACHE_TTL", "45") or "45").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 45
    return max(0, min(ttl, 300))


def review_feedback_cache_ttl_seconds() -> int:
    raw_value = str(os.getenv("PROJECT_APPROVAL_REVIEW_FEEDBACK_CACHE_TTL", "45") or "45").strip()
    try:
        ttl = int(raw_value)
    except ValueError:
        ttl = 45
    return max(0, min(ttl, 300))


def _review_feedback_cache_key(category: str, scene: str = SCENE_INITIATION) -> str:
    return f"{normalize_scene(scene)}:{str(category or '').strip()}"


def load_cached_review_feedback(category: str, scene: str = SCENE_INITIATION) -> dict[str, Any] | None:
    ttl_seconds = review_feedback_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return None
    cache_key = _review_feedback_cache_key(category, scene)
    if not cache_key:
        return None
    now = time.monotonic()
    with _REVIEW_FEEDBACK_CACHE_LOCK:
        record = _REVIEW_FEEDBACK_CACHE.get(cache_key)
        if not record:
            return None
        if float(record.get("expires_at") or 0) <= now:
            _REVIEW_FEEDBACK_CACHE.pop(cache_key, None)
            return None
        payload = record.get("payload")
        if isinstance(payload, dict):
            return json.loads(json.dumps(payload, ensure_ascii=False))
    return None


def store_cached_review_feedback(category: str, payload: dict[str, Any], scene: str = SCENE_INITIATION) -> None:
    ttl_seconds = review_feedback_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return
    cache_key = _review_feedback_cache_key(category, scene)
    if not cache_key:
        return
    with _REVIEW_FEEDBACK_CACHE_LOCK:
        _REVIEW_FEEDBACK_CACHE[cache_key] = {
            "expires_at": time.monotonic() + ttl_seconds,
            "payload": json.loads(json.dumps(payload, ensure_ascii=False)),
        }


def invalidate_review_feedback_cache(category: str, scene: str = SCENE_INITIATION) -> None:
    cache_key = _review_feedback_cache_key(category, scene)
    if not cache_key:
        return
    with _REVIEW_FEEDBACK_CACHE_LOCK:
        _REVIEW_FEEDBACK_CACHE.pop(cache_key, None)


def _architecture_review_cache_key(project_id: str, scene: str = SCENE_INITIATION) -> str:
    return f"{normalize_scene(scene)}:{str(project_id or '').strip()}"


def load_cached_architecture_reviews(
    project_id: str,
    scene: str = SCENE_INITIATION,
) -> list[dict[str, Any]] | None:
    ttl_seconds = architecture_review_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return None
    cache_key = _architecture_review_cache_key(project_id, scene)
    if not cache_key:
        return None
    now = time.monotonic()
    with _ARCH_REVIEW_CACHE_LOCK:
        record = _ARCH_REVIEW_CACHE.get(cache_key)
        if not record:
            return None
        if float(record.get("expires_at") or 0) <= now:
            _ARCH_REVIEW_CACHE.pop(cache_key, None)
            return None
        groups = record.get("groups")
        if isinstance(groups, list):
            return json.loads(json.dumps(groups, ensure_ascii=False))
    return None


def store_cached_architecture_reviews(
    project_id: str,
    groups: list[dict[str, Any]],
    scene: str = SCENE_INITIATION,
) -> None:
    ttl_seconds = architecture_review_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return
    cache_key = _architecture_review_cache_key(project_id, scene)
    if not cache_key:
        return
    with _ARCH_REVIEW_CACHE_LOCK:
        _ARCH_REVIEW_CACHE[cache_key] = {
            "expires_at": time.monotonic() + ttl_seconds,
            "groups": json.loads(json.dumps(groups, ensure_ascii=False)),
        }
