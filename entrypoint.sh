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

# Step 4: Optional in-container Celery (worker+beat) — opt-in via RUN_CELERY=1.
# OFF by default: prod runs dedicated celery-worker / celery-beat containers on
# the same broker, and celery beat has no cross-scheduler lock — a second beat
# here would enqueue every due periodic task twice (t_61b74dc9).
RUN_CELERY="${RUN_CELERY:-0}"
if [ "$RUN_CELERY" = "1" ]; then
    echo "[4/5] Starting Celery Worker (concurrency=1)..."
    celery -A ksms worker --loglevel=info --concurrency=1 &

    echo "[5/5] Starting Celery Beat..."
    celery -A ksms beat --loglevel=info &
else
    echo "[4/5] RUN_CELERY != 1 -> skipping in-container Celery (dedicated celery-worker/celery-beat containers own it)"
fi

# Step 5: Start gunicorn
echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn ksms.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120
