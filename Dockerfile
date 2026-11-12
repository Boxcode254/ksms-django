# KSMS Production Dockerfile v17 — non-root + cap drops; adds weasyprint system deps (t_a6091609)
FROM python:3.11.9-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements-prod.txt --no-cache-dir

COPY . .

RUN mkdir -p /app/logs /app/media /app/staticfiles && \
    addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 --no-create-home appuser && \
    chown -R appuser:appgroup /app

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

USER appuser

CMD ["/app/entrypoint.sh"]
