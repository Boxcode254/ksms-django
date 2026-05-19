# =============================================================================
# KSMS Production Dockerfile — Multi-stage build
# =============================================================================

# ─── Stage 1: Build Tailwind CSS ─────────────────────────────────────────────
FROM node:20-alpine AS tailwind-builder

WORKDIR /app

COPY theme/static_src/package.json theme/static_src/package-lock.json ./theme/static_src/
RUN cd theme/static_src && npm ci

COPY theme/static_src/ ./theme/static_src/
RUN cd theme/static_src && npm run build

# ─── Stage 2: Python dependencies ────────────────────────────────────────────
FROM python:3.11-slim AS python-deps

WORKDIR /install

COPY requirements-prod.txt ./
RUN pip install --prefix=/install -r requirements-prod.txt --no-cache-dir

# ─── Stage 3: Production image ───────────────────────────────────────────────
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=python-deps /install /usr/local

COPY . .

COPY --from=tailwind-builder /app/theme/static_src/dist ./theme/static_src/dist

RUN python manage.py collectstatic --noinput \
    && python manage.py tailwind build --no-input 2>/dev/null || true

RUN adduser --disabled-password --no-create-home ksms \
    && mkdir -p /app/logs /app/media \
    && chown -R ksms:ksms /app

USER ksms

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["gunicorn", "ksms.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--access-logfile", "-", "--error-logfile", "-"]
