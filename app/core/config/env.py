from __future__ import annotations

import os
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)).resolve()
PROJECT_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT
ENV_PATH = PROJECT_ROOT / ".env"


def load_env_file(env_path: Path | None = None) -> None:
    path = env_path or ENV_PATH
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env_file()
