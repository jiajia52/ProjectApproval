from __future__ import annotations

import email
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from collections import deque
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = PROJECT_ROOT / "dist" / "ProjectApproval-linux-offline"
ARCHIVE_PATH = PROJECT_ROOT / "dist" / "ProjectApproval-linux-offline.tar.gz"
WHEELHOUSE_DIR = DIST_DIR / "wheelhouse"
TARGET_PLATFORM = "manylinux2014_x86_64"
TARGET_PYTHON = "3.11"
TARGET_ABI = "cp311"
WHEEL_METADATA_CACHE: dict[Path, tuple[str, str, list[str]]] = {}


def run(command: list[str], *, cwd: Path | None = None) -> None:
    resolved_command = list(command)
    if resolved_command and resolved_command[0] == "npm":
        npm_command = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm_command:
            raise FileNotFoundError("未找到 npm 或 npm.cmd，请先安装 Node.js 并确保 npm 在 PATH 中。")
        resolved_command[0] = npm_command
    print(f"> {' '.join(resolved_command)}")
    subprocess.run(resolved_command, cwd=str(cwd or PROJECT_ROOT), check=True)


def parse_requirements(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirements.append(Requirement(line))
    return requirements


def linux_target_environment() -> dict[str, str]:
    env = default_environment()
    env.update(
        {
            "implementation_name": "cpython",
            "implementation_version": TARGET_PYTHON,
            "os_name": "posix",
            "platform_machine": "x86_64",
            "platform_python_implementation": "CPython",
            "platform_release": "",
            "platform_system": "Linux",
            "platform_version": "",
            "python_full_version": f"{TARGET_PYTHON}.9",
            "python_version": TARGET_PYTHON,
            "sys_platform": "linux",
        }
    )
    return env


def parse_wheel_metadata(wheel_path: Path) -> tuple[str, str, list[str]]:
    cached = WHEEL_METADATA_CACHE.get(wheel_path)
    if cached is not None:
        return cached
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        payload = archive.read(metadata_name).decode("utf-8")
    message = email.message_from_string(payload)
    package_name = message.get("Name", "")
    version = message.get("Version", "")
    dependencies = message.get_all("Requires-Dist") or []
    result = (package_name, version, dependencies)
    WHEEL_METADATA_CACHE[wheel_path] = result
    return result


def find_existing_wheel(requirement: Requirement) -> Path | None:
    package_key = canonicalize_name(requirement.name)
    for wheel_path in sorted(WHEELHOUSE_DIR.glob("*.whl")):
        package_name, version, _ = parse_wheel_metadata(wheel_path)
        if canonicalize_name(package_name) != package_key:
            continue
        if requirement.specifier and version not in requirement.specifier:
            continue
        return wheel_path
    return None


def download_requirement(requirement: Requirement) -> Path:
    existing_wheel = find_existing_wheel(requirement)
    if existing_wheel is not None:
        return existing_wheel

    download_spec = requirement.name
    if requirement.specifier:
        download_spec = f"{download_spec}{requirement.specifier}"

    before = {path.name for path in WHEELHOUSE_DIR.glob("*.whl")}
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(WHEELHOUSE_DIR),
        "--no-deps",
        "--only-binary=:all:",
        "--retries",
        "8",
        "--timeout",
        "120",
        "--platform",
        TARGET_PLATFORM,
        "--implementation",
        "cp",
        "--python-version",
        TARGET_PYTHON.replace(".", ""),
        "--abi",
        TARGET_ABI,
        download_spec,
    ]
    for attempt in range(1, 4):
        try:
            run(command)
            break
        except subprocess.CalledProcessError:
            if attempt == 3:
                raise
            time.sleep(3)
    after = {path.name for path in WHEELHOUSE_DIR.glob("*.whl")}
    new_files = sorted(after - before)
    if not new_files:
        existing_wheel = find_existing_wheel(requirement)
        if existing_wheel is not None:
            return existing_wheel
        raise RuntimeError(f"下载 {download_spec} 后未找到新增 wheel。")
    return WHEELHOUSE_DIR / new_files[-1]


def resolve_linux_dependency_lock(requirements_path: Path) -> list[tuple[str, str]]:
    target_env = linux_target_environment()
    queue: deque[Requirement] = deque(parse_requirements(requirements_path))
    resolved: dict[str, tuple[str, str]] = {}

    while queue:
        requirement = queue.popleft()
        if requirement.marker and not requirement.marker.evaluate(target_env):
            continue

        package_key = canonicalize_name(requirement.name)
        if package_key in resolved:
            if requirement.specifier and resolved[package_key][1] not in requirement.specifier:
                raise RuntimeError(
                    f"Linux 依赖约束冲突: {requirement.name}{requirement.specifier} 与已选版本 {resolved[package_key][1]}"
                )
            continue

        wheel_path = download_requirement(requirement)
        package_name, version, dependencies = parse_wheel_metadata(wheel_path)
        if requirement.specifier and version not in requirement.specifier:
            raise RuntimeError(f"下载结果不满足约束: {package_name}=={version} not in {requirement.specifier}")

        resolved[package_key] = (package_name, version)
        for raw_dependency in dependencies:
            dependency = Requirement(raw_dependency)
            if dependency.marker and not dependency.marker.evaluate(target_env):
                continue
            queue.append(dependency)

    return sorted(resolved.values(), key=lambda item: canonicalize_name(item[0]))


def clean_output() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    WHEELHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    if ARCHIVE_PATH.exists():
        ARCHIVE_PATH.unlink()


def copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, dirs_exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_launcher_scripts() -> None:
    install_script = """#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Existing virtualenv found: $ROOT_DIR/.venv"
  exit 0
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "Missing python3.11/python3. Please install Python 3.11+ first."
    exit 1
  fi
fi

"$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/pip" install --no-index --find-links "$ROOT_DIR/wheelhouse" -r "$ROOT_DIR/requirements-linux-lock.txt"
echo "Offline dependencies installed."
"""
    run_script = """#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  "$ROOT_DIR/install_offline.sh"
fi

export PROJECT_APPROVAL_OPEN_BROWSER="${PROJECT_APPROVAL_OPEN_BROWSER:-false}"
exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/desktop_launcher.py"
"""
    write_text(DIST_DIR / "install_offline.sh", install_script)
    write_text(DIST_DIR / "run.sh", run_script)
    os.chmod(DIST_DIR / "install_offline.sh", 0o755)
    os.chmod(DIST_DIR / "run.sh", 0o755)


def write_runtime_templates() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    if "PROJECT_APPROVAL_OPEN_BROWSER=" not in env_example:
      env_example = f"{env_example.rstrip()}\nPROJECT_APPROVAL_OPEN_BROWSER=false\n"
    write_text(DIST_DIR / ".env.example", env_example)
    write_text(DIST_DIR / ".env", env_example)
    write_text(DIST_DIR / "runtime" / "config" / "integration_config.json", "{}\n")
    write_text(
        DIST_DIR / "README-LINUX.txt",
        "\n".join(
            [
                "ProjectApproval Linux Offline Bundle",
                "",
                "1. 解压 tar.gz 到 Linux 目录。",
                "2. 按需编辑同级 .env 和 runtime/config/integration_config.json。",
                "3. 执行 ./run.sh。",
                "4. 首次运行会离线安装依赖，不访问公网。",
                "",
                "前置条件：",
                "- Linux x86_64",
                "- Python 3.11+ 已安装（python3.11 或 python3）",
                "",
                "外部可配置文件：",
                "- .env",
                "- runtime/config/integration_config.json",
                "- data/*.xlsx",
            ]
        ),
    )


def write_lock_file(lock_items: list[tuple[str, str]]) -> None:
    content = "\n".join(f"{name}=={version}" for name, version in lock_items) + "\n"
    write_text(DIST_DIR / "requirements-linux-lock.txt", content)


def package_archive() -> None:
    with tarfile.open(ARCHIVE_PATH, "w:gz") as archive:
        archive.add(DIST_DIR, arcname=DIST_DIR.name)


def main() -> None:
    clean_output()
    run(["npm", "run", "build"], cwd=FRONTEND_DIR)

    lock_items = resolve_linux_dependency_lock(PROJECT_ROOT / "requirements.txt")

    copy_tree(PROJECT_ROOT / "app", DIST_DIR / "app")
    copy_tree(PROJECT_ROOT / "data", DIST_DIR / "data")
    copy_tree(PROJECT_ROOT / "frontend" / "dist", DIST_DIR / "frontend" / "dist")
    copy_tree(PROJECT_ROOT / "skills", DIST_DIR / "skills")
    copy_tree(PROJECT_ROOT / "scripts", DIST_DIR / "scripts")
    shutil.copy2(PROJECT_ROOT / "desktop_launcher.py", DIST_DIR / "desktop_launcher.py")
    shutil.copy2(PROJECT_ROOT / "requirements.txt", DIST_DIR / "requirements.txt")

    write_lock_file(lock_items)
    write_runtime_templates()
    write_launcher_scripts()
    package_archive()
    print(f"Linux offline bundle generated at: {DIST_DIR}")
    print(f"Archive generated at: {ARCHIVE_PATH}")


if __name__ == "__main__":
    main()
