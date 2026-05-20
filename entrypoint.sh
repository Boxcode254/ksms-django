#!/bin/sh
set -e

echo "=== KSMS Startup ==="
echo "PORT: $PORT"
echo "DEBUG: $DEBUG"
echo "DB_HOST: $DB_HOST"
echo "===================="

# Step 1: Start gunicorn immediately so healthcheck passes
echo "Starting gunicorn on port ${PORT:-8000}..."
gunicorn ksms.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 &
GUNICORN_PID=$!

# Step 2: Run migrations in background
echo "Running migrations..."
python manage.py migrate --noinput &
MIGRATE_PID=$!

# Step 3: Collect static files in background
echo "Collecting static files..."
python manage.py collectstatic --noinput &

# Step 4: Wait for migrations, then create superuser
wait $MIGRATE_PID
if [ -n "$FINAL_SUPERUSER_USERNAME" ] && [ -n "$FINAL_SUPERUSER_PASSWORD" ]; then
    echo "Setting up superuser..."
    python manage.py launch_prep_accounts \
        --demo-action deactivate \
        --final-username "$FINAL_SUPERUSER_USERNAME" \
        --final-email "${FINAL_SUPERUSER_EMAIL:-admin@ksms.local}" \
        --final-password "$FINAL_SUPERUSER_PASSWORD" \
        --dry-run 2>/dev/null || true
    python manage.py launch_prep_accounts \
        --demo-action deactivate \
        --final-username "$FINAL_SUPERUSER_USERNAME" \
        --final-email "${FINAL_SUPERUSER_EMAIL:-admin@ksms.local}" \
        --final-password "$FINAL_SUPERUSER_PASSWORD" || true
    echo "Superuser setup complete."
fi

# Wait for gunicorn to keep container alive
wait $GUNICORN_PID
