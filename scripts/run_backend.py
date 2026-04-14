from __future__ import annotations

import atexit
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config.env import ENV_PATH, load_runtime_env


_FRONTEND_PROCESS: subprocess.Popen[str] | None = None


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def frontend_source_dir() -> Path:
    return PROJECT_ROOT / "frontend"


def frontend_dev_server_url() -> str:
    return os.getenv("PROJECT_APPROVAL_FRONTEND_DEV_SERVER", "http://127.0.0.1:5173").rstrip("/")


def backend_server_url() -> str:
    host = os.getenv("PROJECT_APPROVAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("PROJECT_APPROVAL_PORT", "8000") or 8000)
    return f"http://{host}:{port}"


def frontend_dev_mode_enabled() -> bool:
    mode = os.getenv("PROJECT_APPROVAL_FRONTEND_MODE", "dev").strip().lower()
    return mode != "dist"


def backend_server_available() -> bool:
    try:
        with urlopen(f"{backend_server_url()}/api/health", timeout=0.35) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


def frontend_server_available() -> bool:
    try:
        with urlopen(f"{frontend_dev_server_url()}/ui/", timeout=0.35) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


def frontend_start_command() -> list[str]:
    configured = os.getenv("PROJECT_APPROVAL_FRONTEND_DEV_COMMAND", "").strip()
    if configured:
        return shlex.split(configured, posix=os.name != "nt")

    npm_executable = "npm.cmd" if os.name == "nt" else "npm"
    resolved_npm = shutil.which(npm_executable) or npm_executable
    return [resolved_npm, "run", "dev"]


def stop_frontend_process() -> None:
    global _FRONTEND_PROCESS
    if _FRONTEND_PROCESS is None:
        return
    if _FRONTEND_PROCESS.poll() is None:
        _FRONTEND_PROCESS.terminate()
    _FRONTEND_PROCESS = None


def ensure_frontend_started() -> None:
    global _FRONTEND_PROCESS

    if not frontend_dev_mode_enabled():
        return

    frontend_dir = frontend_source_dir()
    if not frontend_dir.exists():
        raise RuntimeError(f"Frontend source directory not found: {frontend_dir}")

    if frontend_server_available():
        print(f"Frontend dev server already running at {frontend_dev_server_url()}")
        return

    command = frontend_start_command()
    print(f"Starting frontend dev server: {' '.join(command)}")
    _FRONTEND_PROCESS = subprocess.Popen(
        command,
        cwd=str(frontend_dir),
    )
    atexit.register(stop_frontend_process)

    deadline = time.monotonic() + float(os.getenv("PROJECT_APPROVAL_FRONTEND_START_TIMEOUT", "20") or 20)
    while time.monotonic() < deadline:
        if frontend_server_available():
            print(f"Frontend dev server ready at {frontend_dev_server_url()}")
            return
        if _FRONTEND_PROCESS.poll() is not None:
            raise RuntimeError("Frontend dev server exited before becoming ready.")
        time.sleep(0.25)

    raise RuntimeError(f"Frontend dev server did not become ready within timeout: {frontend_dev_server_url()}")


def start_frontend_after_backend_ready() -> None:
    if not frontend_dev_mode_enabled():
        return

    deadline = time.monotonic() + float(os.getenv("PROJECT_APPROVAL_BACKEND_START_TIMEOUT", "60") or 60)
    while time.monotonic() < deadline:
        if backend_server_available():
            ensure_frontend_started()
            return
        time.sleep(0.25)

    raise RuntimeError(f"Backend server did not become ready within timeout: {backend_server_url()}")


if __name__ == "__main__":
    load_runtime_env(ENV_PATH)
    threading.Thread(target=start_frontend_after_backend_ready, daemon=True).start()
    reload_enabled = parse_bool(os.getenv("PROJECT_APPROVAL_RELOAD"), default=True)
    uvicorn.run(
        "app.main:app",
        host=os.getenv("PROJECT_APPROVAL_HOST", "127.0.0.1"),
        port=int(os.getenv("PROJECT_APPROVAL_PORT", "8000") or 8000),
        reload=reload_enabled,
        reload_dirs=[str(PROJECT_ROOT / "app"), str(PROJECT_ROOT / "scripts")] if reload_enabled else None,
    )
