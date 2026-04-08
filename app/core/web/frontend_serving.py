from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from app.core.config.paths import FRONTEND_DIR, PROJECT_ROOT

FRONTEND_DEV_SERVER_URL = os.getenv("PROJECT_APPROVAL_FRONTEND_DEV_SERVER", "http://127.0.0.1:5173").rstrip("/")


def _source_frontend_available() -> bool:
    source_dir = PROJECT_ROOT / "frontend"
    return source_dir.exists() and (source_dir / "package.json").exists() and (source_dir / "src").exists()


def _default_frontend_mode() -> str:
    if getattr(sys, "frozen", False):
        return "dist"
    return "dev" if _source_frontend_available() else "dist"


FRONTEND_MODE = os.getenv(
    "PROJECT_APPROVAL_FRONTEND_MODE",
    _default_frontend_mode(),
).strip().lower()
_FRONTEND_DEV_STATUS_LOCK = threading.Lock()
_FRONTEND_DEV_STATUS = {"checked_at": 0.0, "available": False}


def active_frontend_dir() -> Path:
    candidates: list[Path] = [
        FRONTEND_DIR,
        PROJECT_ROOT / "frontend" / "dist",
        PROJECT_ROOT / "frontend",
        PROJECT_ROOT.parent / "frontend" / "dist",
        PROJECT_ROOT.parent / "frontend",
    ]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        meipass_path = Path(str(meipass)).resolve()
        candidates.extend(
            [
                meipass_path / "frontend" / "dist",
                meipass_path / "frontend",
                meipass_path.parent / "frontend" / "dist",
                meipass_path.parent / "frontend",
            ]
        )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "index.html").exists():
            return resolved

    attempted = ", ".join(str(path) for path in seen)
    raise HTTPException(
        status_code=503,
        detail=f"Frontend build assets not found. Tried: {attempted}",
    )


def frontend_index_file() -> Path:
    return active_frontend_dir() / "index.html"


def frontend_source_dir() -> Path:
    return PROJECT_ROOT / "frontend"


def frontend_dev_mode_enabled() -> bool:
    if FRONTEND_MODE == "dist":
        return False
    if FRONTEND_MODE == "dev":
        return True
    return _source_frontend_available()


def ensure_frontend_dev_server() -> None:
    if FRONTEND_MODE == "dev" and not frontend_dev_server_available():
        raise HTTPException(
            status_code=503,
            detail="Frontend dev server not found. Run `cd frontend && npm run dev`.",
        )


def frontend_dev_server_available() -> bool:
    if not frontend_dev_mode_enabled():
        return False

    now = time.monotonic()
    with _FRONTEND_DEV_STATUS_LOCK:
        if now - float(_FRONTEND_DEV_STATUS["checked_at"]) < 2:
            return bool(_FRONTEND_DEV_STATUS["available"])

    probe_url = f"{FRONTEND_DEV_SERVER_URL}/ui/"
    available = False
    try:
        with urlopen(probe_url, timeout=0.35) as response:
            available = response.status < 500
    except (OSError, URLError):
        available = False

    with _FRONTEND_DEV_STATUS_LOCK:
        _FRONTEND_DEV_STATUS["checked_at"] = now
        _FRONTEND_DEV_STATUS["available"] = available

    return available


def frontend_dev_redirect(path: str = "", query: str = "") -> RedirectResponse:
    normalized_path = path.strip("/")
    url = f"{FRONTEND_DEV_SERVER_URL}/ui"
    if normalized_path:
        url = f"{url}/{normalized_path}"
    elif path.endswith("/"):
        url = f"{url}/"
    if query:
        url = f"{url}?{query}"
    return RedirectResponse(url=url, status_code=307)


def resolve_frontend_file(full_path: str) -> Path | None:
    frontend_dir = active_frontend_dir().resolve()
    candidate = (frontend_dir / full_path).resolve()
    if frontend_dir not in candidate.parents and candidate != frontend_dir:
        return None
    if candidate.is_file():
        return candidate
    return None
