from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.env import ENV_PATH, load_env_file


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


if __name__ == "__main__":
    load_env_file(ENV_PATH)
    reload_enabled = parse_bool(os.getenv("PROJECT_APPROVAL_RELOAD"), default=True)
    uvicorn.run(
        "app.main:app",
        host=os.getenv("PROJECT_APPROVAL_HOST", "127.0.0.1"),
        port=int(os.getenv("PROJECT_APPROVAL_PORT", "8000") or 8000),
        reload=reload_enabled,
        reload_dirs=[str(PROJECT_ROOT / "app"), str(PROJECT_ROOT / "scripts")] if reload_enabled else None,
    )
