# AGENTS.md

FastAPI + SQLAlchemy 2.0 async 脚手架。Python 3.12，uv 包管理。

## 常用命令

```bash
# 本地开发（首次）
cp .env .env.local           # 复制生产基线，编辑本地覆盖
# 编辑 .env.local：至少 DATABASE__AUTO_MIGRATE=true，按需改连接串

# 本地开发（日常）——经 __main__ 加载 Settings（host/port/reload）
APP_ENV=local uv run python -m src.app.main

# Docker 部署
docker compose up -d

# 查看 API 文档
# http://localhost:8000/docs
```

## 技术栈

- Python 3.12 + FastAPI + SQLAlchemy 2.0 async + asyncpg
- Pydantic v2 + pydantic-settings（配置层叠：`.env` 生产基线 -> `.env.{APP_ENV}` 环境覆盖 -> 运行时环境变量）
- Loguru 日志
- uv 包管理器（**必须用 uv，不要用 pip**）
- uuid-utils（UUID v7 主键）

## 项目结构

- `main.py` — 唯一组装入口（`python -m src.app.main`）
- `core/` — 基础设施（config / crypto / logging / database / redis）
- `db/` — 迁移实现（读项目根 `db/` SQL）
- `models/` — SQLAlchemy DB model（继承 BaseDBModel）
- `schemas/` — Pydantic 请求/响应 schema
- `api/` — FastAPI 路由
- `services/` — 业务逻辑
- `middleware/` / `exceptions/` — 横切关注点

## 数据库迁移

| 文件 | 位置 | 说明 |
|------|------|------|
| 迁移 SQL | `db/V{n}__{描述}.sql` | DDL / 种子统一放此；示例见 V3/V4，按需可删 |
| 执行工具 | `migrate.py` | CLI 迁移工具 |
| 自动迁移 | `DATABASE__AUTO_MIGRATE=true` | 启动时自动执行 |

```bash
# 查看待执行
uv run python migrate.py --check
# 执行迁移
uv run python migrate.py
# 查看版本状态
uv run python migrate.py --status
```

生产环境默认 `auto_migrate=false`，手动执行。本地（`.env.local`）与测试环境配置（`.env.test`）默认 `auto_migrate=true`。

## 接口约定

- JSON 默认 camelCase（`APP__JSON_CAMEL_CASE=true`，与 Java 对齐）；需要 snake_case 时设为 `false`
- 只用 GET 和 POST，不用 PUT/DELETE/PATCH
- 统一响应 `Result<T>`（code, data, message, timestamp）
- 主键用 UUID v7（`uuid_utils.uuid7()`）
- 数据库 session 通过 `Depends(get_session)` 注入（`app.core.database`）
- 单例用 `@lru_cache`

## 密钥管理（强制）

**禁止将数据库密码、Redis 密码、SSO client_secret、MinIO 密钥等以明文写入可提交的 `.env`。**

| 规则 | 说明 |
|------|------|
| 提交格式 | 敏感值必须是 `ENC(密文)`，用加密脚本生成后再写入 `.env` |
| 加密工具 | 脚手架仓库 `scripts/secret.py`（Fernet）；生成项目后可从 scaffold 拷贝或继续用该脚本 |
| 解密密钥 | 环境变量 `CONFIG_KEY`，存密码管理器，**永不提交 git** |
| 启动行为 | `Settings` 经 `EncStr` / `crypto.decrypt` 自动解密，业务代码无感知 |
| 可提交 | 含 `ENC(...)` 的 `.env`、`.env.test` 等 |
| 不可提交 | 明文密钥、`CONFIG_KEY`、`.env.local` |

```bash
# 在 scaffold 仓库或拷贝 secret.py 后执行
export CONFIG_KEY="<团队共享密钥，来自密码管理器>"
python scripts/secret.py generate                 # 管理员首次生成密钥
python scripts/secret.py encrypt "真实密码"         # → ENC(...)
# 将 ENC(...) 写入 .env，例如：
# DATABASE__URL=postgresql://app:ENC(...)@localhost:5432/mydb
# REDIS__URL=redis://:ENC(...)@localhost:6379/0
```

与 Java 侧 Jasypt 密文**不互通**。细节见 `docs/配置管理规范.md`。

## 关联规范文档

| 文档 | 说明 |
|------|------|
| `docs/接口设计规范.md` | HTTP 方法规范、参数传递规范、camelCase 开关 |
| `docs/数据库规范.md` | 表命名、字段类型、SQLAlchemy Model 规范 |
| `docs/编码规范.md` | 新增实体流程、Model/Schema 分离、统一响应 |
| `docs/测试规则.md` | 单元/集成测试编写与运行（pytest） |
| `docs/配置管理规范.md` | 配置层叠（含 `APP_ENV=test` 指向 `.env.test`）、密文、ENV 命名 |
