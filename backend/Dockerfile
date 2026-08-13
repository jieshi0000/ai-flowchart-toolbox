FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY src/ ./src/
COPY db/ ./db/
COPY migrate.py ./

ENV PYTHONPATH=/app/src
EXPOSE 8000

# 生产迁移（compose 已注入 backend/.env）：
#   docker compose run --rm backend uv run python migrate.py
CMD ["uv", "run", "python", "-m", "app.main"]
