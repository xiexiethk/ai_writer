FROM node:20-bookworm-slim AS openwps-build
WORKDIR /app/openwps_frontend
COPY openwps_frontend/package*.json ./
RUN npm install
COPY openwps_frontend/ ./
COPY openwps_server /app/openwps_server
# 让 tsc 的 outDir 指向 openwps_server/node/.generated/，
# 这里软链 openwps_frontend/server -> /app/openwps_server，使 build:worker 输出最终
# 落到 /app/openwps_server/node/.generated/（后端 _worker_path 期望的位置）。
RUN rm -rf /app/openwps_frontend/server \
 && ln -s /app/openwps_server /app/openwps_frontend/server
RUN npm run build
RUN npm run build:worker

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
      sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wkhtmltopdf \
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY backend /app/backend
COPY openwps_server /app/openwps_server
RUN mkdir -p /app/backend/data /app/backend/uploads /app/backend/parsed_output /app/backend/app/data/images
COPY --from=openwps-build /app/openwps_frontend/dist /app/openwps_frontend/dist
COPY --from=openwps-build /app/openwps_server/node/.generated /app/openwps_server/node/.generated
# Document worker 通过裸名 import 'prosemirror-model' 等运行时依赖。
# Node ESM 解析裸名包时，从 worker 文件目录沿父目录链路向上找 node_modules。
# worker 路径 /app/openwps_server/node/.generated/server/node/document_worker.js
# 它的父目录链路最终能到 /app/，所以把 node_modules 放在 /app/。
COPY --from=openwps-build /app/openwps_frontend/node_modules /app/node_modules

WORKDIR /app/backend
EXPOSE 28000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "28000"]
