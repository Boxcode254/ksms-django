#!/bin/sh
# KSMS start script — same sequence as entrypoint.sh but for non-Docker use
set -e

echo "[1/4] Running database migrations..."
python manage.py migrate --noinput 2>&1 | tail -20

echo "[2/4] Collecting static files..."
python manage.py collectstatic --noinput 2>&1 | tail -5

echo "[3/4] Ensuring superuser..."
python manage.py ensure_superuser 2>&1

echo "[4/4] Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn ksms.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120
