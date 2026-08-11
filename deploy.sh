#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
    echo "错误: .env 不存在，请 cp .env.example .env 并填写配置"
    exit 1
fi

# 加载 .env（docker compose 自动读，这里仅用于获取 INFRA_NET）
set -a; source .env 2>/dev/null; set +a

echo "--- 确保 Docker 网络存在 ---"
docker network inspect "${INFRA_NET:-infra-net}" &>/dev/null || docker network create "${INFRA_NET:-infra-net}"

echo "--- 拉取代码 ---"
# 仅当「当前目录是 git 根」且「存在 origin」时 pull，避免误拉上层仓库（如 drill-output 嵌套在 scaffold 下）
if [ "${SKIP_GIT_PULL:-}" = "1" ]; then
    echo "跳过 git pull（SKIP_GIT_PULL=1）"
elif git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  && [ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$(pwd -P)" ]; then
    if git remote get-url origin &>/dev/null; then
        git pull
    else
        echo "跳过 git pull（无 origin 远端）"
    fi
else
    echo "跳过 git pull（当前目录不是独立 git 仓库根）"
fi

echo "--- 构建镜像 ---"
docker compose build

echo "--- 数据库迁移 ---"
# Python 后端：启动前执行迁移（幂等，已执行的会跳过）
# Java 后端：Flyway 随应用启动自动迁移，无需单独执行
if [ -f "backend/migrate.py" ]; then
    docker compose run --rm flowchart-toolbox-server uv run python migrate.py
fi

echo "--- 启动服务 ---"
docker compose up -d --force-recreate

echo "--- 清理旧镜像 ---"
docker image prune -f

echo "=== 部署完成 ==="
echo "前端: http://localhost:20105"
echo "后端: http://localhost:10105"
