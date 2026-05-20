#!/bin/sh
set -e

echo "=== KSMS Startup ==="
echo "PORT: ${PORT:-8000}"
echo "DEBUG: ${DEBUG:-False}"
echo "DB_HOST: ${DB_HOST:-not set}"
echo "===================="

# Step 1: Run database migrations (must complete before serving traffic)
echo "[1/4] Running database migrations..."
python manage.py migrate --noinput 2>&1 | tail -20
echo "      Migrations complete."

# Step 2: Collect static files (WhiteNoise needs the manifest before gunicorn)
echo "[2/4] Collecting static files..."
python manage.py collectstatic --noinput 2>&1 | tail -5
echo "      Static files collected."

# Step 3: Create superuser if env vars are set (idempotent)
echo "[3/4] Ensuring superuser..."
python manage.py ensure_superuser 2>&1
echo "      Superuser check complete."

# Step 4: Start gunicorn
echo "[4/4] Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn ksms.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120
