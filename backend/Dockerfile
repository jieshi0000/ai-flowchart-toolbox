FROM node:22-alpine AS mermaid-assets

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories \
    && apk add --no-cache tar
RUN npm config set registry https://registry.npmmirror.com
RUN mkdir -p /tmp/mermaid /tmp/mermaid/extracted /out \
    && npm pack mermaid@11.16.1 --pack-destination /tmp/mermaid \
    && tar -xzf /tmp/mermaid/mermaid-11.16.1.tgz -C /tmp/mermaid/extracted --strip-components=1 \
    && cp /tmp/mermaid/extracted/dist/mermaid.min.js /out/mermaid.min.js

FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        chromium \
        fontconfig \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

COPY --from=mermaid-assets /out/mermaid.min.js /app/assets/mermaid.min.js

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY fonts/ ./fonts/
RUN mkdir -p /usr/share/fonts/flowchart/Inter /usr/share/fonts/flowchart/SourceHanSansSC \
    && cp fonts/Inter/*.ttf /usr/share/fonts/flowchart/Inter/ \
    && cp fonts/SourceHanSansSC/*.otf /usr/share/fonts/flowchart/SourceHanSansSC/ \
    && fc-cache -fv

COPY src/ ./src/
COPY db/ ./db/
COPY migrate.py ./

ENV PYTHONPATH=/app/src
ENV FLOWCHART_CHROMIUM_PATH=/usr/bin/chromium
EXPOSE 8000

# 生产迁移（compose 已注入 backend/.env）：
#   docker compose run --rm backend uv run python migrate.py
CMD ["uv", "run", "python", "-m", "app.main"]
