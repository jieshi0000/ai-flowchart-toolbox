#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass() { echo -e "${GREEN}✅ $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }

if [ ! -f ".env" ]; then
  fail ".env 不存在，请先 cp .env.example .env"
fi

set -a; source .env 2>/dev/null; set +a

BACKEND_PORT="${BACKEND_PORT:-10105}"
FRONTEND_PORT="${FRONTEND_PORT:-20105}"
BASE_URL="http://localhost:${BACKEND_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

echo "=== 连通性测试 ==="

# 确保本地中间件已启动
if [ -f "docker-compose.infra.yml" ]; then
  if ! docker compose -f docker-compose.infra.yml ps --status running 2>/dev/null | grep -q postgres; then
    echo "--- 启动 docker-compose.infra.yml ---"
    docker compose -f docker-compose.infra.yml up -d
    sleep 5
  fi
  pass "docker-compose.infra.yml 中间件已启动"
fi

# 后端健康检查
HEALTH_URL="${BASE_URL}/api/public/health"
echo "--- GET ${HEALTH_URL} ---"
HEALTH_RESP=$(curl -sf --max-time 10 "${HEALTH_URL}" || true)
if echo "${HEALTH_RESP}" | grep -q '"status"'; then
  pass "后端 health: ${HEALTH_RESP}"
else
  fail "后端 health 接口不可达或返回异常: ${HEALTH_RESP:-empty}"
fi

# Demo 分页
DEMO_URL="${BASE_URL}/api/demo/page?pageNum=1&pageSize=5"
echo "--- GET ${DEMO_URL} ---"
DEMO_RESP=$(curl -sf --max-time 10 "${DEMO_URL}" || true)
if echo "${DEMO_RESP}" | grep -qE '"code":\s*200'; then
  pass "demo/page 正常"
else
  # 若开启认证可能 401，仍算连通
  if echo "${DEMO_RESP}" | grep -qE '401|未登录|未认证|Not Login'; then
    pass "demo/page 可达（需认证）"
  else
    fail "demo/page 异常: ${DEMO_RESP:-empty}"
  fi
fi

# 前端连通性
echo "--- GET ${FRONTEND_URL} ---"
FRONTEND_RESP=$(curl -sf --max-time 10 "${FRONTEND_URL}" || true)
if [ -n "$FRONTEND_RESP" ]; then
  pass "前端可达: ${FRONTEND_URL}"
else
  fail "前端不可达: ${FRONTEND_URL}"
fi

echo "=== 全部通过 ==="
