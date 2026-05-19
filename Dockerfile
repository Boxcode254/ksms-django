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

COPY requirements-prod.txt ./
RUN pip install -r requirements-prod.txt --no-cache-dir

COPY . .

# Collect static files (pre-built CSS is already committed)
RUN python manage.py collectstatic --noinput

RUN adduser --disabled-password --no-create-home ksms \
    && mkdir -p /app/logs /app/media \
    && chown -R ksms:ksms /app

USER ksms

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

CMD ["gunicorn", "ksms.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--access-logfile", "-", "--error-logfile", "-"]
