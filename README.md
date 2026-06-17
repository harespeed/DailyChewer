# DailyChewer

DailyChewer 是一个本地优先的日报优化工具，提供三套入口：

- CLI：适合个人日常使用、脚本和 cron
- FastAPI backend：适合 Web UI 和自动化系统接入
- React Web UI：适合上传、预览、保存和检索

它会读取 `csv`、`xlsx`、`markdown`、`docx` 日报，基于真实内容生成结构化日报，并继续汇总为周报和月报。

## Project Structure

```text
DailyChewer/
├── backend/                 # 共享业务逻辑、认证、数据库、FastAPI API
│   ├── dailychewer_backend/ # parser / llm / storage / report / services / db / auth
│   └── api/                 # FastAPI routes 和 schemas
├── cli/                     # Typer CLI 入口
├── frontend/                # React + Vite + TypeScript + Ant Design
├── data/                    # 原始日报、优化日报、周报、月报、日志、索引
├── input/                   # 用户准备导入的日报文件
└── examples/                # 预留示例目录
```

说明：
- `backend`：CLI 和 Web API 共享的核心实现。
- `cli`：只做参数解析、交互确认和 rich 输出。
- `frontend`：上传、预览、保存、搜索和汇总的 Web 界面。
- `data`：本地持久化目录，不依赖数据库。
- `input`：放用户待导入的文件。

## Multi-user Mode

Web API 默认使用 PostgreSQL 作为多用户元数据存储。

- 每个用户只能看到自己的日报、周报、月报和上传文件。
- 文件按 `data/users/{user_id}/...` 隔离保存。
- Web 上传、搜索、周报、月报和下载都基于当前登录用户过滤。
- 原来的 `data/index.json` 仍保留，作为 CLI local mode 的 legacy 存储。

## Features

- 导入 `csv`、`xlsx`、`md`、`markdown`、`docx`
- 调用 MiniMax 或任意 OpenAI-compatible API
- 敏感信息脱敏后再发送给 LLM
- 生成结构化优化日报并打质量分
- 生成周报、月报，支持多种导出格式
- 支持项目和标签分类
- 支持历史搜索
- 支持日报模板生成
- 支持 Docker CLI、FastAPI、React Web UI

## Installation

建议使用 Python 3.11。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

命令说明：
- `python -m venv .venv`：创建虚拟环境。
- `source .venv/bin/activate`：激活虚拟环境。
- `pip install -e .`：以可编辑模式安装 CLI、backend API 依赖。

第一次运行前建议创建目录：

```bash
mkdir -p input data
```

命令说明：
- `input`：放用户要导入的日报文件。
- `data`：保存日报、周报、月报、日志和索引。

运行测试：

```bash
pip install -e ".[dev]"
pytest
```

## Environment Configuration

在项目根目录创建 `.env`，可参考 `.env.example`。

```env
# Option A: MiniMax
MINIMAX_API_KEY=your_minimax_api_key
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-M2.7

# Option B: OpenAI-compatible
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# Database
DATABASE_URL=postgresql+psycopg://dailychewer:dailychewer_password@postgres:5432/dailychewer

# Auth
JWT_SECRET_KEY=change_this_secret_in_production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

DAILYCHEWER_CREATE_DEFAULT_USER=true
DAILYCHEWER_DEFAULT_USERNAME=admin
DAILYCHEWER_DEFAULT_PASSWORD=admin123
DAILYCHEWER_DEFAULT_DISPLAY_NAME=Admin
```

说明：
- 如果同时配置 `MINIMAX_API_KEY` 和 `OPENAI_API_KEY`，默认优先使用 MiniMax。
- `MINIMAX_BASE_URL` 中国区常见可改为 `https://api.minimaxi.com/v1`。
- 具体 model name 以你的供应商控制台为准。
- 没有任何 API Key 时，会提示：
  `No LLM API key configured. Please set MINIMAX_API_KEY or OPENAI_API_KEY in .env.`
- 如果 `DATABASE_URL` 未配置，CLI 仍可继续使用 local mode 和 `data/index.json`。

## Docker Compose Entrypoints

项目提供两个分开的 Compose 文件：

- `docker-compose-gui.yml`：启动 PostgreSQL、backend、React GUI。
- `docker-compose-cli.yml`：启动 PostgreSQL、backend，并进入交互式 CLI/TUI。

两个文件都使用同一个 Compose project name：`dailychewer`。因此如果 GUI 已经启动了 `dailychewer-backend-1`，再启动 CLI 时会复用同一个 backend；反过来也一样，不会再启动第二套 backend。

一键构建并启动 GUI：

```bash
scripts/start_dailychewer.sh
```

一键构建并进入 CLI/TUI：

```bash
scripts/start_dailychewer.sh --cli
```

只构建镜像：

```bash
scripts/start_dailychewer.sh --build-only
```

跳过构建，只启动 GUI：

```bash
scripts/start_dailychewer.sh --no-build --gui
```

启动 GUI：

```bash
COMPOSE_IGNORE_ORPHANS=true docker compose -f docker-compose-gui.yml up -d backend frontend
```

打开：

```text
http://localhost:5173
```

进入 CLI/TUI：

```bash
COMPOSE_IGNORE_ORPHANS=true docker compose -f docker-compose-cli.yml run --rm cli
```

说明：
- 如果 backend/postgres 尚未启动，CLI compose 会先启动它们。
- 如果 backend/postgres 已由 GUI compose 启动，CLI compose 会检测并复用现有容器。
- `COMPOSE_IGNORE_ORPHANS=true` 只用于隐藏另一个 compose 文件中服务的 orphan 提示，不会删除容器。

完整 CLI/TUI 功能说明见：

```text
docs/CLI_FULL_GUIDE.md
```
- Web backend 启动需要 `DATABASE_URL`，否则会给出清晰错误。
- 生产环境必须修改 `JWT_SECRET_KEY` 和默认 admin 密码。

## Configuration File: `dailychewer.toml`

项目根目录可选放置 `dailychewer.toml`。优先级为：

`CLI 参数 > 环境变量 > dailychewer.toml > 默认值`

示例：

```toml
[llm]
provider = "minimax"
model = "MiniMax-M2.7"
base_url = "https://api.minimax.io/v1"

[report]
default_format = "markdown"
default_weekly_style = "concise"
default_monthly_style = "formal"
language = "zh-CN"

[privacy]
enable_redaction = true

[storage]
data_dir = "data"
input_dir = "input"

[behavior]
ask_questions = true
auto_save = false
generate_weekly_after_ingest = false
```

## CLI Usage

版本：

```bash
dailychewer version
```

命令说明：
- `version`：输出当前版本，例如 `DailyChewer 0.1.0`。

环境检查：

```bash
dailychewer doctor
dailychewer doctor --check-api
dailychewer db check
dailychewer db init
```

命令说明：
- `doctor`：检查 Python、目录、索引、LLM、mirror、Docker 环境。
- `--check-api`：额外发一个最小 JSON 请求验证当前 LLM API。
- `db check`：检查 `DATABASE_URL`、数据库连通性、Alembic revision、`users` 表和 active admin。
- `db init`：执行数据库初始化，优先跑 Alembic，必要时回退到 metadata create-all，并按配置创建默认 admin。

用户管理：

```bash
dailychewer user create admin --password admin123 --display-name Admin --admin
dailychewer user list
dailychewer user disable USERNAME
dailychewer user enable USERNAME
dailychewer user reset-password USERNAME --password NEW_PASSWORD
```

命令说明：
- `user create`：创建数据库用户，密码会哈希后保存。
- `user list`：列出所有用户，不显示 `password_hash`。
- `user disable` / `user enable`：启用或禁用用户，不删除数据。
- `user reset-password`：重置用户密码，不输出明文密码。
- 这些命令是本地管理员工具，不要暴露给不可信用户。

生成日报模板：

```bash
dailychewer template --date 2026-06-03 --format markdown
dailychewer template --date 2026-06-03 --format docx --output input/2026-06-03.docx
dailychewer template --date 2026-06-03 --format markdown --user admin
```

命令说明：
- `--date`：模板日期。
- `--format`：`markdown/csv/xlsx/docx`。
- `--output`：自定义输出路径。
- `--user`：使用数据库中的指定用户作用域，文件写入 `data/users/{user_id}/templates/`。

导入日报：

```bash
dailychewer ingest ./input/example.md
dailychewer ingest ./input/example.md --date 2026-06-03 --save --no-weekly --no-questions
dailychewer ingest ./input/example.md --date 2026-06-03 --project AI-App --tag automation --tag api --save --no-weekly --no-questions
dailychewer ingest ./input/example.md --date 2026-06-03 --user admin --project AI-App --save --no-weekly --no-questions
```

命令说明：
- `--save`：跳过保存确认，直接保存。
- `--no-weekly`：导入后不询问是否生成周报。
- `--no-questions`：跳过追问，直接生成保守版本。
- `--project`：写入项目分类。
- `--tag`：可以多次传入标签。
- `--user`：切换到数据库用户作用域；需要 `DATABASE_URL` 已配置，且该用户已存在。

查看日报：

```bash
dailychewer list
dailychewer list --week 2026-W23
dailychewer list --project AI-App
dailychewer list --tag automation
dailychewer list --user admin
```

搜索历史日报：

```bash
dailychewer search "错误码"
dailychewer search "错误码" --project AI-App --tag automation
dailychewer search "错误码" --from 2026-06-01 --to 2026-06-30 --limit 10
dailychewer search "错误码" --user admin
```

命令说明：
- `QUERY`：关键词。
- `--week` / `--from` / `--to`：控制范围。
- `--project` / `--tag`：按分类过滤。

生成周报：

```bash
dailychewer weekly --week 2026-W23 --format docx
dailychewer weekly --from 2026-06-01 --to 2026-06-07 --format markdown --no-delete-prompt
dailychewer weekly --week 2026-W23 --format markdown --style formal --preview
dailychewer weekly --week 2026-W23 --format markdown --style formal --user admin
```

命令说明：
- `--format`：`markdown/docx/xlsx/csv`。
- `--style`：`concise/formal/detailed/interview`。
- `--preview`：先终端预览，再决定是否保存。
- `--delete-after-export`：显式危险删除。
- `--yes` 不会触发删除。

生成月报：

```bash
dailychewer monthly --month 2026-06 --format markdown --style formal
dailychewer monthly --month 2026-06 --format markdown --style formal --user admin
```

命令说明：
- `--month`：月份，格式 `YYYY-MM`。
- `--style`：同周报。

清理某周：

```bash
dailychewer clean --week 2026-W23
```

迁移旧 index：

```bash
dailychewer migrate-index --user admin
dailychewer migrate-index --user admin --apply
dailychewer migrate-index --user admin --apply --copy-files
```

命令说明：
- 默认 dry-run，只统计将迁移多少条。
- `--apply`：真正写入 PostgreSQL。
- `--copy-files`：把 legacy 文件复制到 `data/users/{user_id}/legacy/`，便于后续安全下载。

## Daily Quality Score

优化日报会基于原始日报生成质量分，满分 25 分：

- 工作内容清晰度
- 结果/进展明确度
- 问题描述完整度
- 解决方案明确度
- 个人成长体现度

评分只基于原始日报，不会编造。

## Weekly Report Styles

- `concise`：简洁提交版
- `formal`：正式汇报版
- `detailed`：详细复盘版
- `interview`：更适合面试叙述的表达方式

这些 style 只改变表达，不会增加原日报中不存在的事实。

## Sensitive Information Redaction

默认开启脱敏，发送给 LLM 前会替换：

- 邮箱：`example@example.com` -> `[REDACTED_EMAIL]`
- 中国手机号：`13812345678` -> `[REDACTED_PHONE]`
- `sk-...` / `api_key=...` -> `[REDACTED_API_KEY]`
- `token=...` / `bearer ...` -> `[REDACTED_TOKEN]`

说明：
- 原始文件仍原样保存在 `data/raw/`。
- 日志不会记录原文全文。

## Logs

默认日志文件：

```text
data/logs/dailychewer.log
```

日志级别可配置：

```env
DAILYCHEWER_LOG_LEVEL=DEBUG
```

## PostgreSQL Setup

Docker 启动 PostgreSQL：

```bash
docker compose up postgres
```

命令说明：
- `postgres`：启动 PostgreSQL 16，并使用 `postgres_data` volume 持久化数据。

推荐初始化流程：

```bash
cp .env.example .env
docker compose up -d postgres
docker compose run --rm dailychewer db init
docker compose up backend frontend
```

说明：
- 先复制 `.env.example` 为 `.env`。
- 启动前务必修改 `JWT_SECRET_KEY` 和默认 admin 密码。
- `db init` 会检查连接、升级 schema，并按配置创建默认 admin。

执行数据库迁移：

```bash
alembic upgrade head
docker compose run --rm backend alembic upgrade head
```

命令说明：
- `alembic upgrade head`：把数据库迁移到最新结构。
- Docker 场景下建议先执行迁移，再启动 backend。

真实 PostgreSQL 自检脚本：

```bash
python scripts/pg_smoke_test.py
```

说明：
- 读取 `DATABASE_URL`。
- 连接数据库并写入两名测试用户的数据。
- 验证 user A 查不到 user B 的记录。

## Default Admin User

如果 `.env` 中设置：

```env
DAILYCHEWER_CREATE_DEFAULT_USER=true
DAILYCHEWER_DEFAULT_USERNAME=admin
DAILYCHEWER_DEFAULT_PASSWORD=admin123
DAILYCHEWER_DEFAULT_DISPLAY_NAME=Admin
```

backend 启动时会在数据库中自动创建默认 admin 用户，但只会创建一次。

强提醒：
- 生产环境必须修改默认密码。
- 首次登录后应立即更换默认 admin 密码。

## Production-like Multi-user Setup

推荐按下面顺序初始化多用户部署：

```bash
cp .env.example .env
# 修改 JWT_SECRET_KEY 和默认 admin 密码
docker compose up -d postgres
docker compose run --rm dailychewer db init
docker compose up backend frontend
```

说明：
- `postgres`：启动 PostgreSQL 数据库容器。
- `db init`：创建或升级 schema，并准备默认 admin。
- `backend` / `frontend`：启动 FastAPI 和 React Web UI。

## Backend API

本地启动：

```bash
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

参数说明：
- `uvicorn`：FastAPI 的 ASGI server。
- `backend.api.main:app`：FastAPI app 路径。
- `--reload`：代码变化后自动重启。
- `--host 0.0.0.0`：允许局域网或 Docker 外部访问。
- `--port 8000`：监听 8000 端口。

如果数据库尚未初始化，backend 会提示先执行：

```bash
alembic upgrade head
```

关键接口：

- `GET /api/health`
- `GET /api/doctor`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/change-password`
- `GET /api/users/me`
- `GET /api/users`
- `PATCH /api/users/{user_id}/status`
- `POST /api/ingest/preview`
- `POST /api/ingest/save`
- `GET /api/reports`
- `GET /api/search`
- `POST /api/weekly`
- `POST /api/monthly`
- `POST /api/template`
- `GET /api/files/{file_id}/download`

说明：
- 除 `health`、`doctor`、`auth` 外，其余接口都需要登录。
- 文件下载推荐使用 `file_id` 方式，由后端校验当前用户 owner。
- `GET /api/users` 和 `PATCH /api/users/{user_id}/status` 只有 admin 用户可访问。

## Frontend Development

本地启动前端：

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

命令说明：
- `cp .env.example .env`：写入前端本地 API 地址配置。
- `npm install`：安装 React、Vite、Ant Design 等依赖。
- `npm run dev`：启动 Vite 开发服务器。

默认访问：

```text
http://localhost:5173
```

前端 API 地址通过 `VITE_API_BASE_URL` 控制，默认指向：

```text
http://localhost:8000
```

## Frontend npm Mirror

如果 `npm install` 在国内网络环境失败，可以先切换 npm 源：

```bash
npm config set registry https://registry.npmmirror.com
```

命令说明：
- `npm`：Node.js 包管理器。
- `config set registry`：设置 npm 下载源。
- `https://registry.npmmirror.com`：国内常用 npm 镜像源。

恢复官方源：

```bash
npm config set registry https://registry.npmjs.org/
```

Docker Compose 下可通过环境变量覆盖：

```bash
NPM_CONFIG_REGISTRY=https://registry.npmmirror.com docker compose build frontend
NPM_CONFIG_REGISTRY=https://registry.npmjs.org/ docker compose build frontend
```

## Web App Usage

先启动 PostgreSQL、backend 和 frontend：

```bash
docker compose up postgres backend frontend
```

访问：

```text
http://localhost:5173
```

页面包含：

- Upload Daily
- Reports
- Weekly
- Monthly
- Search
- Template
- Doctor

## Login and Register

首次打开 Web UI 时会先进入登录页。

流程：

1. 输入用户名和密码登录。
2. 如果还没有账户，可切换到 Register 注册。
3. 登录成功后，前端会把 access token 保存到 `localStorage`。
4. 之后上传、搜索、周报、月报、下载都只作用于当前用户。

说明：
- 前端不会保存密码。
- 当前 MVP 用 `localStorage` 保存 token；生产环境建议改成 `httpOnly cookie`。
- 如果 token 过期或接口返回 `401`，前端会自动清空本地 token，并提示 `Session expired, please log in again.`

## Change Password

登录后可在 Web UI 的 `Account` 页面修改密码。

流程：
- 输入旧密码。
- 输入新密码。
- 提交后后端校验旧密码并更新 `password_hash`。

## Admin Users Page

如果当前用户 `is_admin=true`，前端会显示 `Admin Users` 页面。

功能：
- 查看所有用户
- 查看 `is_active` / `is_admin`
- 启用或禁用普通用户

说明：
- 非 admin 用户不会看到该页面。
- 后端也会做 `403` 权限校验。

## Upload Files from Web UI

Web UI 支持两种上传方式：

- 点击上传
- 拖拽上传

支持文件类型：

- `csv`
- `xlsx`
- `md`
- `markdown`
- `docx`

流程：

1. 在 Upload Daily 页面选择或拖拽文件。
2. 输入日期、项目、标签。
3. 点击 `Preview & Optimize`。
4. 查看优化结果和质量分。
5. 如有追问，补充回答。
6. 点击 `Save Report`。

说明：
- 上传和保存都需要先登录。
- 文件会先进入当前用户的 `data/users/{user_id}/uploads/tmp/`。
- 真正保存后，raw / optimized / weekly / monthly 文件也都按用户目录隔离。

## Docker Web Usage

构建 Python 镜像：

```bash
docker compose build
```

CLI 仍可单独运行：

```bash
docker compose run --rm dailychewer version
docker compose run --rm dailychewer ingest /app/input/example.md --date 2026-06-03 --save --no-weekly --no-questions
docker compose run --rm dailychewer ingest /app/input/example.md --date 2026-06-03 --user admin --save --no-weekly --no-questions
```

启动 Web：

```bash
docker compose up postgres backend frontend
```

命令说明：
- `postgres`：启动 PostgreSQL。
- `backend`：启动 FastAPI。
- `frontend`：启动 React Vite dev server。

前端本地环境变量示例：

```bash
cp frontend/.env.example frontend/.env
```

## Build Frontend with Docker

前端开发镜像单独构建：

```bash
docker compose build frontend
docker compose up frontend
```

命令说明：
- `build frontend`：构建前端开发镜像，并在镜像构建阶段安装依赖。
- `up frontend`：启动 Vite dev server。
- Compose 会挂载 `./frontend:/app` 和独立的 `/app/node_modules`，避免每次启动都重复安装依赖。

## Build in Mainland China

Docker build 默认启用国内 mirror：

- Debian apt：Tsinghua
- PyPI：Tsinghua

直接构建：

```bash
docker compose build
```

强制启用国内源：

```bash
USE_CHINA_MIRROR=true docker compose build
```

切回官方源：

```bash
USE_CHINA_MIRROR=false docker compose build
```

也可以在 `.env` 中设置：

```env
USE_CHINA_MIRROR=false
```

## Change Mirrors

可以在 `.env` 中修改：

```env
APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
PIP_TRUSTED_HOST=mirrors.tuna.tsinghua.edu.cn
```

阿里云 PyPI：

```env
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
PIP_TRUSTED_HOST=mirrors.aliyun.com
```

中科大 PyPI：

```env
PIP_INDEX_URL=https://mirrors.ustc.edu.cn/pypi/simple/
PIP_TRUSTED_HOST=mirrors.ustc.edu.cn
```

腾讯云 PyPI：

```env
PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
PIP_TRUSTED_HOST=mirrors.cloud.tencent.com
```

## Docker Hub Pull Acceleration

如果连 `python:3.11-slim` 都拉不下来，这不是 DailyChewer Dockerfile 的问题，而是 Docker Hub 网络问题。

处理思路：

1. 打开 Docker Desktop Settings。
2. 找到 Docker Engine。
3. 在 `daemon.json` 中配置 `registry-mirrors`。
4. `Apply & Restart`。
5. 重新执行 `docker compose build`。

注意：
- 第三方 Docker Hub proxy 可用性会变化。
- 企业或私有镜像不要通过不可信 proxy 拉取。
- 公共基础镜像可以加速，但要关注供应链安全。

## Local pip Mirror without Docker

如果你本地 `pip install` 也需要切换镜像：

```bash
pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
```

命令说明：
- `pip`：Python 包管理器。
- `config set`：写入 pip 配置。
- `global.index-url`：设置全局下载源。

恢复官方源：

```bash
pip config unset global.index-url
```

## Security Notes

- `JWT_SECRET_KEY` 必须修改，不要在生产环境继续使用示例值。
- 默认 admin 密码必须修改。
- API Key 只保存在 backend `.env` 中，前端不会接触 LLM API Key。
- 下载接口必须通过后端鉴权，且只允许访问当前用户目录内的已授权文件。
- `.env` 不要提交到 Git。
- `localStorage` token 只是 MVP 方案，生产环境建议改成 `httpOnly cookie`。

## Security Checklist

- 修改 `JWT_SECRET_KEY`。
- 修改默认 admin 密码。
- 不要提交 `.env`。
- 不要把 CLI `user` 管理命令暴露给不可信用户。
- 生产环境建议启用 HTTPS。
- 生产环境建议使用 `httpOnly cookie` 替代 `localStorage` token。
- 定期备份 PostgreSQL volume 和 `data/users/`。

## Full Docker Smoke Test

在有 Docker daemon 的环境中运行：

```bash
bash scripts/docker_smoke_test.sh
bash scripts/docker_smoke_test.sh --with-frontend
```

说明：
- 会依次验证 `postgres`、`db init`、`backend health`
- 验证 register / login / `auth/me`
- 验证未登录访问 `/api/reports` 返回 `401`
- 验证已登录访问 `/api/reports` 的基础链路
- `--with-frontend` 会额外启动并检查 `http://localhost:5173`
- 这是本机 Docker 联调脚本，不是 CI/CD 配置

## PostgreSQL Smoke Test

在已配置 `DATABASE_URL` 的环境中运行：

```bash
python scripts/pg_smoke_test.py
```

说明：
- 创建 `smoke_user_a` 和 `smoke_user_b`
- 分别写入 fake `daily_report`
- 验证 list 和 search 都按 `user_id` 隔离
- 最后清理测试数据

如果没有配置 `DATABASE_URL`，脚本会输出提示并退出，不会修改任何数据。

## Local Production Check

本机发布前可以运行：

```bash
bash scripts/release_check.sh
```

说明：
- 这个脚本只用于本机检查，不接入 CI/CD
- 会执行 Python 编译检查、`pytest`、前端 `npm run build`
- 会检查 `docker compose config`
- 会执行 `python -m dailychewer.cli version` 和 `doctor`
- 如果本机 Docker daemon 可用，还会尝试构建 `dailychewer` 和 `backend` 镜像

## Troubleshooting npm ENOTFOUND

如果看到：

```text
npm error code ENOTFOUND
npm error syscall getaddrinfo
```

通常是 DNS 或 npm registry 访问问题。

可按顺序排查：
- 设置 npm 国内源
- 检查 DNS
- 检查代理设置
- 重新运行 `npm install`
- Docker 下设置 `NPM_CONFIG_REGISTRY`

## Backup

建议至少备份两类数据：

- `postgres_data` volume：保存用户、元数据、认证信息和报表索引。
- `data/users/`：保存用户原始日报、优化日报、周报、月报、模板和临时上传文件。

## Backup and Restore

创建备份：

```bash
dailychewer backup create --output backups/
dailychewer backup create --output backups/ --include-logs
dailychewer backup create --output backups/ --skip-db
dailychewer backup create --output backups/ --zip
dailychewer backup create --output backups/ --zip --remove-dir-after-zip
```

命令说明：
- `backup create`：创建一份时间戳备份目录。
- `--output`：备份输出目录。
- `--include-logs`：是否同时备份 `data/logs/`。
- `--skip-db`：不执行数据库导出。
- `--skip-files`：不备份本地文件。
- `--zip`：额外生成 zip 归档，适合长期保存。
- `--remove-dir-after-zip`：zip 生成后删除原始备份目录。

每次创建备份时都会生成 `backup_manifest.json`，用于：
- 记录备份内容
- 保存每个文件的 `sha256` 和 `size_bytes`
- 支持恢复前冲突检查和完整性校验

`backup_manifest.json` 不会记录数据库密码，只会保留数据库 host 和库名等非敏感信息。

## Backup Verify

校验备份目录或 zip：

```bash
dailychewer backup verify backups/xxx
dailychewer backup verify backups/xxx.zip
```

说明：
- 会读取 `backup_manifest.json`
- 检查 manifest 中记录的文件是否存在
- 重新计算 `sha256`
- 检查 `size_bytes`
- 全部通过时会输出 `Backup verification passed.`

恢复备份：

```bash
dailychewer backup restore backups/xxx
dailychewer backup restore backups/xxx --apply
dailychewer backup restore backups/xxx --apply --restore-files
dailychewer backup restore backups/xxx --apply --restore-db --confirm-overwrite-db
dailychewer backup restore backups/xxx --apply --restore-files --overwrite-files
dailychewer backup restore backups/xxx.zip
```

命令说明：
- 默认是 dry-run，只展示将恢复的内容。
- `--apply`：真正执行恢复。
- `--restore-files`：只恢复文件。
- `--restore-db`：只恢复数据库。
- `--confirm-overwrite-db`：明确允许覆盖已有数据库内容。
- `--overwrite-files`：明确允许覆盖内容不同的现有文件。

## Restore Conflict Check

`backup restore` 的安全默认行为：
- 默认 dry-run，不会写入任何数据。
- 如果目标文件已存在：
  - 内容相同：标记为 `same`
  - 内容不同：标记为 `conflict`
- 文件冲突默认不会覆盖，必须显式传 `--overwrite-files`
- 数据库如果检测到 `users / daily_reports / weekly_reports / monthly_reports` 中已有数据，默认不会覆盖
- 只有传入 `--confirm-overwrite-db` 才允许恢复数据库 dump

这套设计是为了降低误恢复和误覆盖风险。

## CLI Local Mode

默认 CLI 仍然走本地模式，不依赖 PostgreSQL：

```bash
dailychewer ingest ./input/example.md
dailychewer list
dailychewer weekly --week 2026-W23 --format markdown
```

说明：
- 元数据继续写入 `data/index.json`。
- 文件继续写入 `data/raw`、`data/optimized`、`data/weekly`、`data/monthly`。

## CLI Database User Mode

如果已经配置 `DATABASE_URL`，并且数据库中存在该用户，可以用：

```bash
dailychewer ingest ./input/example.md --user admin
dailychewer list --user admin
dailychewer search "错误码" --user admin
dailychewer weekly --week 2026-W23 --user admin
dailychewer monthly --month 2026-06 --user admin
dailychewer template --date 2026-06-03 --user admin
```

说明：
- `--user` 会把 CLI 切换到该数据库用户作用域。
- 文件保存到 `data/users/{user_id}/...`。
- 这是本地管理模式，不适合暴露给不可信用户。

## Migrate Legacy `index.json`

如果你之前一直用 CLI local mode，可以把旧的 `data/index.json` 迁移到某个数据库用户：

```bash
dailychewer migrate-index --user admin
dailychewer migrate-index --user admin --apply
dailychewer migrate-index --user admin --apply --copy-files
```

说明：
- 默认 dry-run，不写数据库。
- `--apply` 后会把 legacy `reports / weekly_reports / monthly_reports` 写入 PostgreSQL。
- `--copy-files` 会把旧文件复制到 `data/users/{user_id}/legacy/`，后续更容易通过受保护下载接口访问。
- 不会删除旧 `data/index.json`。

## Idempotent Legacy Migration

`migrate-index` 可以重复执行：

```bash
dailychewer migrate-index --user admin --apply
dailychewer migrate-index --user admin --apply
```

说明：
- 已迁移过的 legacy 记录会通过 deterministic `migration_id`、migration metadata 和目标用户范围检查自动跳过。
- 输出中会显示 `skipped_existing`。
- dry-run 输出中也会显示本次迁移涉及的 `migration_id`。

## Safe Copy for Legacy Files

使用：

```bash
dailychewer migrate-index --user admin --apply --copy-files
```

说明：
- legacy 文件会复制到 `data/users/{user_id}/legacy/...`
- 文件名会带时间戳和路径 hash
- 已存在时还会自动追加计数
- 不会覆盖已有文件

## File Isolation

Web 多用户模式下，文件保存在：

```text
data/users/{user_id}/raw/{iso_week}/...
data/users/{user_id}/optimized/{iso_week}/...
data/users/{user_id}/weekly/{iso_week}/...
data/users/{user_id}/monthly/{month}/...
data/users/{user_id}/uploads/tmp/...
data/users/{user_id}/templates/...
```

说明：
- 用户 A 看不到用户 B 的文件。
- 下载接口会按 `current_user.id` 校验 owner。
- 前端不会直接暴露 `data/` 目录。

## CLI and Web Shared Backend

CLI 和 Web API 都调用：

```text
backend/dailychewer_backend/services/
```

这里是真正的共享业务逻辑：

- `ingest_service.py`
- `weekly_service.py`
- `monthly_service.py`
- `search_service.py`
- `template_service.py`
- `doctor_service.py`

因此：

- CLI 不会重复实现 ingest / weekly / monthly / search 业务逻辑
- Web API 也不会再实现一套同名逻辑

## Example End-to-End

本地 CLI：

```bash
dailychewer template --date 2026-06-03 --format markdown
dailychewer ingest ./input/example.md --date 2026-06-03 --project AI-App --tag automation --save --no-weekly --no-questions
dailychewer weekly --week 2026-W23 --format markdown --style formal
dailychewer monthly --month 2026-06 --format markdown --style formal
dailychewer search "错误码"
```

Docker Web：

```bash
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up postgres backend frontend
```

## Limitations

- Web 上传保存阶段当前会再次调用一次 ingest service，MVP 里还没有做 preview cache。
- 完整多用户集成测试当前主要用 SQLite 跑单元和 API 测试；真实 PostgreSQL 联调需要在本机或 Docker 环境执行迁移后再验证。
- 前端当前是 Vite dev server，不是生产静态构建部署方案。
- `npm run build` 需要先安装前端依赖。
- 没有配置 API Key 时，上传和生成类功能会返回清晰错误，不会直接 traceback。
