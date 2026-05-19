# KSMS Production Dockerfile v6
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements-prod.txt --no-cache-dir

# Copy application code
COPY . .

# Create runtime directories
RUN mkdir -p /app/logs /app/media /app/staticfiles

EXPOSE 8000

# Collect static at startup (needs env vars), then start gunicorn
CMD sh -c "python manage.py collectstatic --noinput --clear 2>/dev/null || true && gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile - --error-logfile - --timeout 120"
