FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev libmagic1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements-prod.txt --no-cache-dir
COPY . .
RUN mkdir -p /app/logs /app/media /app/staticfiles

EXPOSE 8000
CMD ["sh", "-c", "gunicorn ksms.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --access-logfile - --error-logfile - --timeout 120 --log-level debug"]
