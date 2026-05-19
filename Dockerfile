# =============================================================================
# KSMS Production Dockerfile
# =============================================================================

FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements-prod.txt --no-cache-dir

COPY . .

RUN mkdir -p /app/logs /app/media /app/staticfiles \
    && chmod +x entrypoint.sh

RUN adduser --disabled-password --gecos "" ksms \
    && chown -R ksms:ksms /app

USER ksms

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
