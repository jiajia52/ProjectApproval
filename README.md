# ProjectApproval

项目已按 `auto_approval` 的方式重构为根目录分层结构：

- `app/`：FastAPI 服务、审批引擎、LLM 审批链路、前端静态页面
- `skills/`：根目录审批技能，按评审规则说明的大类生成，每个大类一个 `SKILL.md`
- `data/`：`product_info`、API 列表、规则矩阵、样例输入
- `scripts/`：启动、规则抽取、项目生成、技能生成、接口抓取脚本
- `runtime/`：运行时产物、审批落盘、接口样本、日志、配置

## 启动

先准备环境变量：

```powershell
Copy-Item .env.example .env
```

启动后端：

```powershell
.\.venv\Scripts\python.exe scripts\run_backend.py
```

Windows EXE 打包：
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts\build_windows_exe.py
```

打包完成后的可运行目录：`dist/ProjectApproval/`
- 启动文件：`ProjectApproval.exe`
- 外部环境变量配置：`dist/ProjectApproval/.env`
- 外部远程接口配置：`dist/ProjectApproval/runtime/config/integration_config.json`

访问页面：

- `http://127.0.0.1:8000/ui/approval.html`
- `http://127.0.0.1:8000/ui/skills.html`

兼容入口 `http://127.0.0.1:8000/ui/rules.html` 会自动跳转到 `skills.html`。

## 常用脚本

生成审批项目、本体和规则包：

```powershell
.\.venv\Scripts\python.exe scripts\build_project_approval_bundle.py
```

重新生成根目录审批技能：

```powershell
.\.venv\Scripts\python.exe scripts\generate_approval_item_skills.py
```

抓取 iwork 原始接口返回：

```powershell
.\.venv\Scripts\python.exe scripts\dump_iwork_api_responses.py --max-projects 3
```

指定项目抓取：

```powershell
.\.venv\Scripts\python.exe scripts\dump_iwork_api_responses.py --project-id <项目ID>
```

## 运行产物

- `runtime/review_rules.json`
- `runtime/project_approval_project.json`
- `runtime/project_approval_ontology.json`
- `runtime/project_approval_ontology.ttl`
- `runtime/approval_runs/`
- `runtime/api_dumps/`
- `runtime/logs/`
- `runtime/config/`

## 兼容入口

旧入口仍可用：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```
