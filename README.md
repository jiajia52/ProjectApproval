# ProjectApproval

项目审批辅助系统，包含 FastAPI 后端、Vite 前端、审批规则生成脚本，以及按审批点拆分的技能目录。

## 目录结构

- `app/`：后端主代码。
- `frontend/`：前端工程。
  - `frontend/src/`：React/Vite 源码。
  - `frontend/dist/`：前端构建产物，不入库。
- `materials/`：按立项、任务单、验收拆分的材料目录。
- `docs/`：项目级说明文档与整体方案文档。
- `runtime/`：运行时产物目录。
  - `runtime/config/skill_config.json`：项目使用的技能生成配置，保留入库。
  - `runtime/config/integration_config.json`：本地远程接口配置，不入库。
  - 其余 `approval_runs`、`api_result`、`project_documents` 等目录均为本地产物。
- `scripts/`：启动、打包、规则抽取、技能生成等脚本。
- `skills/`：按审批点生成的技能文件。

## 启动方式

先准备环境变量：

```powershell
Copy-Item .env.example .env
```

启动后端：

```powershell
.\.venv\Scripts\python.exe scripts\run_backend.py
```

默认访问地址：

- `http://127.0.0.1:8000/ui/approval`
- `http://127.0.0.1:8000/ui/skills`

注意：

- 后端只会提供 `frontend/dist/` 中已经构建好的前端静态资源。
- 如果前端未构建，先执行 `cd frontend` 和 `npm run build`。

## 前端开发

开发模式：

```powershell
cd frontend
npm install
npm run dev
```

构建前端：

```powershell
cd frontend
npm run build
```

## 常用脚本

生成审批规则与项目产物：

```powershell
.\.venv\Scripts\python.exe scripts\build_project_approval_bundle.py
```

重新生成审批技能：

```powershell
.\.venv\Scripts\python.exe scripts\generate_approval_item_skills.py
```

抓取远程接口返回：

```powershell
.\.venv\Scripts\python.exe scripts\dump_iwork_api_responses.py --max-projects 3
```

## 打包

Windows EXE：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts\build_windows_exe.py
```

打包输出目录：`dist/ProjectApproval/`

## 文件整理约定

- 不提交 `build/`、`dist/`、`frontend/node_modules/`、`frontend/dist/`。
- 不提交 `runtime/` 下的运行结果、缓存、日志和接口落盘文件。
- 不提交本地敏感配置，例如 `runtime/config/integration_config.json` 和 `.env`。
- `runtime/config/skill_config.json` 作为项目配置保留入库。
