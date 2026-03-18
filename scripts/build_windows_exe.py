from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = PROJECT_ROOT / "dist" / "ProjectApproval"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_DIR = BUILD_DIR / "pyinstaller"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    resolved_command = list(command)
    if resolved_command and resolved_command[0] == "npm":
        npm_command = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm_command:
            raise FileNotFoundError("未找到 npm 或 npm.cmd，请先安装 Node.js 并确保 npm 在 PATH 中。")
        resolved_command[0] = npm_command
    print(f"> {' '.join(resolved_command)}")
    subprocess.run(resolved_command, cwd=str(cwd or PROJECT_ROOT), check=True)


def ensure_pyinstaller() -> None:
    try:
        __import__("PyInstaller")
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PyInstaller 未安装。先执行 `python -m pip install -r requirements-build.txt` 再重试。"
        ) from exc


def clean_output() -> None:
    shutil.rmtree(PROJECT_ROOT / "dist", ignore_errors=True)
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    spec_path = PROJECT_ROOT / "ProjectApproval.spec"
    if spec_path.exists():
        spec_path.unlink()


def copy_tree(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Missing required path: {source}")
    shutil.copytree(source, target, dirs_exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_runtime_templates() -> None:
    write_text(DIST_DIR / ".env.example", (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8"))
    write_text(DIST_DIR / ".env", (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8"))
    write_text(DIST_DIR / "runtime" / "config" / "integration_config.json", json.dumps({}, ensure_ascii=False, indent=2))
    write_text(
        DIST_DIR / "README-EXE.txt",
        "\n".join(
            [
                "ProjectApproval Windows EXE",
                "",
                "1. 双击 ProjectApproval.exe 启动。",
                "2. 首次启动前可先编辑同级 .env。",
                "3. 远程接口 token/JSESSIONID 也可在 runtime/config/integration_config.json 中维护，",
                "   或启动后在“审批工作台”页面保存。",
                "4. 浏览器访问地址默认是 http://127.0.0.1:8000/ui/approval",
                "",
                "可外部修改的关键文件：",
                "- .env",
                "- runtime/config/integration_config.json",
                "- data/*.xlsx",
            ]
        ),
    )


def main() -> None:
    ensure_pyinstaller()
    clean_output()
    run(["npm", "run", "build"], cwd=FRONTEND_DIR)
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "ProjectApproval",
            "--specpath",
            str(SPEC_DIR),
            "--paths",
            str(PROJECT_ROOT / "scripts"),
            "--collect-submodules",
            "app",
            "--collect-all",
            "uvicorn",
            "--collect-all",
            "agentscope",
            "--collect-all",
            "openai",
            "--hidden-import",
            "build_project_approval_bundle",
            "--hidden-import",
            "extract_review_rules",
            "--hidden-import",
            "generate_approval_item_skills",
            str(PROJECT_ROOT / "desktop_launcher.py"),
        ]
    )

    copy_tree(PROJECT_ROOT / "data", DIST_DIR / "data")
    copy_tree(PROJECT_ROOT / "skills", DIST_DIR / "skills")
    copy_tree(PROJECT_ROOT / "frontend" / "dist", DIST_DIR / "frontend" / "dist")
    copy_tree(PROJECT_ROOT / "app" / "frontend", DIST_DIR / "app" / "frontend")
    write_runtime_templates()
    print(f"EXE package generated at: {DIST_DIR}")


if __name__ == "__main__":
    main()
