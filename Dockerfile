# KSMS Production Dockerfile v11
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements-prod.txt --no-cache-dir

COPY . .

RUN mkdir -p /app/logs /app/media /app/staticfiles

EXPOSE 8000

# Run migrations, collect static, then start gunicorn
# Migrations run first to ensure DB schema is up to date
CMD python manage.py migrate --noinput && \
    python manage.py collectstatic --noinput --clear 2>/dev/null || true && \
    gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile - --error-logfile - --timeout 120
