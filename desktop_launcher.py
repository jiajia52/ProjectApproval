from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config.env import ENV_PATH, load_env_file
from app.core.config.paths import CONFIG_DIR, PROJECT_ROOT as ACTIVE_PROJECT_ROOT, RUNTIME_DIR


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def browser_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def ensure_external_layout() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    load_env_file(ENV_PATH)
    ensure_external_layout()

    from app.main import app

    host = os.getenv("PROJECT_APPROVAL_HOST", "127.0.0.1")
    port = int(os.getenv("PROJECT_APPROVAL_PORT", "8000") or 8000)
    auto_open = parse_bool(os.getenv("PROJECT_APPROVAL_OPEN_BROWSER"), default=True)
    url = f"http://{browser_host(host)}:{port}/ui/approval"

    print(f"Project root: {ACTIVE_PROJECT_ROOT}")
    print(f"Runtime dir: {RUNTIME_DIR}")
    print(f"Config dir: {CONFIG_DIR}")
    print(f"Launch URL: {url}")

    if auto_open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
