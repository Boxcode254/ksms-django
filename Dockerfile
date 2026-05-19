# =============================================================================
# KSMS Production Dockerfile — Single-stage build
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

# Copy requirements first for better caching
COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements-prod.txt --no-cache-dir

COPY . .

# Create directories
RUN mkdir -p /app/logs /app/media /app/staticfiles

# Create non-root user
RUN adduser --disabled-password --gecos "" ksms \
    && chown -R ksms:ksms /app

USER ksms

EXPOSE 8000

# Simple healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Start gunicorn directly (collectstatic runs at build time via Railway or is skipped)
CMD ["gunicorn", "ksms.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--access-logfile", "-", "--error-logfile", "-", "--timeout", "120"]
