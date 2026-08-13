# AGENTS.md

本文件为 AI 编码助手提供项目导航入口。开发需求时请先阅读本文件，再按需查阅子目录的规范文档。

## 项目概述

**流程图工具箱** 是基于 Scaffold 生成的全栈项目。

| 层 | 技术栈 | 目录 |
|----|--------|------|
| 后端 | PYTHON | `backend/` |
| 前端 | umi | `frontend/` |
| 数据库 | PostgreSQL 17 | Docker 中间件 |
| 缓存 | Redis 7 | Docker 中间件 |
| 对象存储 | MinIO | Docker 中间件 |

## 文档导航

写代码前，请先查阅对应文档：

| 文档 | 路径 | 何时查阅 |
|------|------|----------|
| **后端编码入口** | `backend/AGENTS.md` | 写后端任何代码前必读 |
| **前端编码入口** | `frontend/AGENTS.md` | 写前端任何代码前必读 |
| 接口设计规范 | `backend/docs/接口设计规范.md` | 新增/修改 API 时 |
| 数据库规范 | `backend/docs/数据库规范.md` | 新增表、字段、索引时 |
| 编码规范 | `backend/docs/编码规范.md` | 写 DO/VO/Service 时 |
| 测试规则 | `backend/docs/测试规则.md` | 写测试用例时 |
| 需求文档 | `docs/需求文档/` | 了解业务需求 |
| 设计文档 | `docs/设计文档/` | 了解架构设计 |
| API 接口文档 | `docs/API接口文档/` | 查看接口约定 |

## 快速启动

```powershell
# 首次使用：复制示例并填写仅限本机的凭据。
# 若该文件不存在，才从示例创建；已有文件不要覆盖。
if (-not (Test-Path docker-compose.local.env)) {
  Copy-Item docker-compose.local.env.example docker-compose.local.env
}
# 无论新建还是已有文件，都必须填写示例中的所有必填 LOCAL_* 变量；留空会启动失败。

# 启动完整本地环境：前端、API、Celery、PG、Redis、MinIO
docker compose --env-file docker-compose.local.env -f docker-compose.local.yml up -d --build

# 或分别启动服务（需要自行准备 PG、Redis、MinIO）
cd backend
uv sync
$env:APP_ENV='local'; uv run python -m app.main

cd ..\frontend
pnpm install
pnpm dev
pnpm run typecheck
```

`docker-compose.local.env` 是受 Git 忽略的本机私有文件；从 `docker-compose.local.env.example` 复制后填写，绝不能提交。`docker-compose.local.yml` 仅使用变量引用，不含凭据，且仅供本地开发。

## 端口

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:20105 |
| 后端 | http://localhost:10105/api |
| API 文档 | http://localhost:10105/api/swagger-ui.html |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| MinIO Console | http://localhost:9001 |

## 前后端联调约定

| 项 | 约定 |
|----|------|
| API 前缀 | `/api` |
| 认证头 | `Authorization: Bearer <token>` |
| 响应格式 | `{ code, data, message, timestamp }`，成功 `code=200` |
| 错误码 | 401=未认证，403=无权限，400=参数错误，500=服务器异常 |
| 字段命名 | camelCase |

## 目录结构

```
flowchart-toolbox/
├── backend/              # 后端（详见 backend/AGENTS.md）
├── frontend/            # 前端（详见 frontend/AGENTS.md）
├── docs/               # 项目文档
├── docker-compose.yml       # 全栈部署
├── docker-compose.dev.yml   # 本地开发中间件
├── docker-compose.local.yml # Day 1 完整本地环境
├── deploy.sh                # 线上部署
└── test-connectivity.sh    # 连通性测试
```
