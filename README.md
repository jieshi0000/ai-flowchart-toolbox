# 流程图工具箱

由 Scaffold 生成的全栈项目（后端: python）。

> **AI 编码助手**：开发需求前请先阅读 [AGENTS.md](./AGENTS.md)，按文档导航查阅对应规范。

## 快速开始

### 1. 启动本地全栈环境

```powershell
# 首次使用：复制示例并填写仅限本机的凭据。
# 若该文件不存在，才从示例创建；已有文件不要覆盖。
if (-not (Test-Path docker-compose.local.env)) {
  Copy-Item docker-compose.local.env.example docker-compose.local.env
}
# 无论新建还是已有文件，都必须填写示例中的所有必填 LOCAL_* 变量；留空会启动失败。
# 编辑 docker-compose.local.env 后启动
docker compose --env-file docker-compose.local.env -f docker-compose.local.yml up -d --build
```

该命令会启动前端、FastAPI、Celery Worker/Beat、PostgreSQL、Redis 与 MinIO，均位于项目内部 Docker 网络。

访问 http://localhost:20105 ，使用本地开发账号登录后进入流程图工作台。健康检查地址为 http://localhost:10105/api/public/health 。

### 2. 本机分别启动（可选）

```powershell
cd backend
uv sync
$env:APP_ENV='local'; uv run python -m app.main

cd ..\frontend
pnpm install
pnpm dev
pnpm run typecheck
```

本机后端需要可用的 PostgreSQL、Redis 与 MinIO；日常开发优先使用上面的完整 Compose 环境。
## VS Code 一键启动

用 VS Code / Cursor 打开本仓库根目录后：

| 入口 | 说明 |
|------|------|
| **Full Stack (local)** | 同时启后端 + 前端（推荐） |
| **Backend (local)** | 仅后端（Python: `APP_ENV=local` / Java: `profile=local`） |
| **Frontend (dev)** | 仅前端（Umi Max development，端口 20105） |

- **Run and Debug**（F5）：选上面三个 launch 配置
- **Terminal → Run Task**：`fullstack:dev` / `backend:dev` / `frontend:dev`

首次前请先完成依赖安装（`backend` 下 `uv sync`；`frontend` 下 `pnpm install`）。分别启动时使用各目录下受忽略的 `.env.local` 私有覆盖；Compose 启动使用受忽略的 `docker-compose.local.env`，两者都禁止提交明文凭据。

## 本地开发

```powershell
# 启动完整本地环境
docker compose --env-file docker-compose.local.env -f docker-compose.local.yml up -d --build

# 停止完整本地环境
docker compose --env-file docker-compose.local.env -f docker-compose.local.yml down

# 查看状态
docker compose --env-file docker-compose.local.env -f docker-compose.local.yml ps
```

`docker-compose.local.env` 是受 Git 忽略的本机私有文件，必须由 `docker-compose.local.env.example` 复制后填写，禁止提交。Compose 模板不包含明文凭据，所有端口仅绑定到 `127.0.0.1`，仅限本地开发。

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
├── docker-compose.local.yml # Day 1 完整本地环境
├── .vscode/                 # launch / tasks（local 缺省）
├── deploy.sh                # 线上部署
└── test-connectivity.sh
```
