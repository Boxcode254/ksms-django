#!/bin/sh
set -e

echo "=== KSMS Startup ==="
echo "PORT: $PORT"
echo "DEBUG: $DEBUG"
echo "DB_HOST: $DB_HOST"
echo "===================="

# Step 1: Run migrations
echo "Running migrations..."
python manage.py migrate --noinput
echo "Migrations complete."

# Step 2: Create/update superuser if credentials provided
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
        --final-password "$FINAL_SUPERUSER_PASSWORD"
    echo "Superuser setup complete."
fi

# Step 3: Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear 2>/dev/null || true
echo "Static files collected."

# Step 4: Start gunicorn
echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn ksms.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120
