# 流程图工具箱

由 Scaffold 生成的全栈项目（后端: python）。

> **AI 编码助手**：开发需求前请先阅读 [AGENTS.md](./AGENTS.md)，按文档导航查阅对应规范。

## 快速开始

默认账号: admin / admin123

### 1. 启动中间件

```bash
docker compose -f docker-compose.dev.yml up -d
```

### 2. 初始化数据库权限

> 仅在**首次启动中间件后**执行一次。若之前已启动过 PostgreSQL（数据卷已存在），init.sql 可能未执行，需要手动跑一次。

```bash
docker exec postgres psql -U app -d flowchart_toolbox_db -f /docker-entrypoint-initdb.d/init.sql
```

### 3. 启动后端

```bash
cd backend
uv sync
APP_ENV=local uv run python -m src.app.main
# PowerShell: $env:APP_ENV='local'; uv run python -m src.app.main
# CMD: set APP_ENV=local && uv run python -m src.app.main
# 首次启动会自动执行数据库迁移（建表+种子数据），后续启动幂等跳过

### 4. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
## VS Code 一键启动

用 VS Code / Cursor 打开本仓库根目录后：

| 入口 | 说明 |
|------|------|
| **Full Stack (local)** | 同时启后端 + 前端（推荐） |
| **Backend (local)** | 仅后端（Python: `APP_ENV=local` / Java: `profile=local`） |
| **Frontend (dev)** | 仅前端（Vite development） |

- **Run and Debug**（F5）：选上面三个 launch 配置
- **Terminal → Run Task**：`fullstack:dev` / `backend:dev` / `frontend:dev`

首次前请先完成依赖安装（`backend` 下 `uv sync` 或 Maven；`frontend` 下 `pnpm install`）。
Python 后端本地覆盖文件为 `backend/.env.local`（setup 已复制并默认 `DATABASE__AUTO_MIGRATE=true`）；Java 用 `application-local.yml`（setup 已从 `.example` 生成，localhost + `flyway.enabled=true`）+ `SPRING_PROFILES_ACTIVE=local`。

## 本地开发

```bash
# 启动中间件
docker compose -f docker-compose.dev.yml up -d

# 停止中间件
docker compose -f docker-compose.dev.yml down

# 查看状态
docker compose -f docker-compose.dev.yml ps
```

## 连通性测试

```bash
./test-connectivity.sh
```

## 全栈部署（需外部 infra-net 中间件）

生产部署依赖已运行的 PG/Redis/MinIO（如 jxaiqtc-infra），打包后的镜像不包含中间件。

```bash
# 1. 环境变量（已填写则跳过）
cp .env.example .env

# 2. 确保根 .env / backend/.env 中的口令与 infra 实际值一致

# 3. 部署（Python 后端 deploy.sh 会自动执行数据库迁移）
./deploy.sh
```

> **deploy.sh 做了什么**：确保 Docker 网络 -> git pull -> 数据库迁移（Python） -> docker compose build -> up -d --force-recreate -> 清理旧镜像。  
> 跳过 git pull：`SKIP_GIT_PULL=1 ./deploy.sh`

## 目录结构

```
flowchart-toolbox/
├── AGENTS.md               # AI 编码入口（文档导航）
├── backend/                 # python 后端
├── frontend/                # 前端（umi）
├── docs/
├── docker-compose.yml       # 全栈部署（连接外部 infra-net）
├── docker-compose.dev.yml   # 本地开发中间件（PG + 选配 Redis/MinIO）
├── docker-compose.infra.yml # 本项目独立中间件（可选）
├── .vscode/                 # launch / tasks（local 缺省）
├── deploy.sh                # 线上部署
└── test-connectivity.sh
```
