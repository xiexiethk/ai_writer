FROM node:20-bookworm-slim AS openwps-build
WORKDIR /app/openwps_frontend
COPY openwps_frontend/package*.json ./
RUN npm install
COPY openwps_frontend/ ./
COPY openwps_server /app/openwps_server
RUN mkdir -p /app/openwps_server/node/.generated
RUN npm run build

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
COPY --from=openwps-build /app/openwps_frontend/server /app/openwps_frontend/server

WORKDIR /app/backend
EXPOSE 28000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "28000"]
