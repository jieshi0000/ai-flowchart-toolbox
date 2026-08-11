#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
    echo "错误: .env 不存在，请复制 .env.example 并修改"
    exit 1
fi

echo "--- 拉取代码 ---"
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

echo "--- 启动服务 ---"
docker compose up -d --force-recreate

echo "--- 清理旧镜像 ---"
docker image prune -f

echo "=== 完成 ==="
