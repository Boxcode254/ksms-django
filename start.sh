#!/bin/sh
# Run collectstatic first (required before gunicorn starts)
python manage.py collectstatic --noinput --clear 2>&1 | tail -5

# Run migrations in background
python manage.py migrate --noinput &
MIGRATE_PID=$!

# Start gunicorn
gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile - --error-logfile - --timeout 120 &

# Wait for migrations, then create superuser
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
wait
