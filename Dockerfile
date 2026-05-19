# =============================================================================
# KSMS Production Dockerfile — Single-stage build
# =============================================================================

FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements-prod.txt --no-cache-dir

COPY . .

# Create directories for runtime
RUN adduser --disabled-password --no-create-home ksms \
    && mkdir -p /app/logs /app/media /app/staticfiles \
    && chown -R ksms:ksms /app

USER ksms

EXPOSE 8000

# Simple healthcheck — just verify the process is listening
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Run collectstatic at startup, then start gunicorn
CMD ["sh", "-c", "python manage.py collectstatic --noinput --verbosity 0 2>/dev/null || true && gunicorn ksms.wsgi:application --bind 0.0.0.0:8000 --workers 4 --access-logfile - --error-logfile - --timeout 120"]
