FROM docker.abrha.net/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://package-mirror.liara.ir/repository/pypi/simple \
    TZ=Asia/Tehran

WORKDIR /app

# Debian Mirrors
RUN sed -i 's|http://deb.debian.org/debian|https://repo.abrha.net/debian|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org/debian-security|https://repo.abrha.net/debian-security|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|https://deb.debian.org/debian|https://repo.abrha.net/debian|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|https://security.debian.org/debian-security|https://repo.abrha.net/debian-security|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        sqlite3 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/data && \
    mkdir -p /app/logs && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]