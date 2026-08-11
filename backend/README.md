# 流程图工具箱 后端

## 本地开发

### 首次初始化

```bash
# 1. 复制生产基线，开始编辑本地覆盖
cp .env .env.local

# 2. 编辑 .env.local，改掉需要覆盖的值：
#    - 数据库连接串（按本机）
#    - DATABASE__AUTO_MIGRATE=true（本地默认应开启）

# 3. 启动（经 __main__ 加载 Settings：host/port/reload）
APP_ENV=local uv run python -m src.app.main
```

### 配置层叠机制

```
.env            生产基线（全量配置，所有键有默认值）
.env.local      个人本地覆盖（只写差异，gitignore）
.env.test       测试环境配置覆盖（只写差异，可提交）
运行时环境变量  最高优先级
```

层叠顺序：`.env` → `.env.{APP_ENV}` → 运行时环境变量，后者覆盖前者，未指定键继承。

- 生产部署不设 `APP_ENV` → 只读 `.env`，安全基线
- 本地开发设 `APP_ENV=local` → `.env` + `.env.local` 合并生效
- 测试环境设 `APP_ENV=test` → `.env` + `.env.test` 合并生效（与 pytest「怎么写测试」无关）

### 常用命令

```bash
# 本地开发（Bash/WSL）
APP_ENV=local uv run python -m src.app.main

# PowerShell / CMD 需分开设置环境变量：
#   $env:APP_ENV='local'; uv run python -m src.app.main
#   CMD: set APP_ENV=local && uv run python -m src.app.main

# Docker 部署
docker compose up -d

# 查看文档（基线端口 8000；本机改口写 .env.local 的 APP__PORT）
open http://localhost:8000/docs
```

## Docker 部署

```bash
docker compose up -d
```

## 技术栈

- Python 3.12 + FastAPI + SQLAlchemy 2.0 async + asyncpg
- Pydantic v2 + pydantic-settings
- Loguru
- uv
- UUID v7
