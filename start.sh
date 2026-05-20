#!/bin/sh
# Run collectstatic first (required before gunicorn starts)
python manage.py collectstatic --noinput --clear 2>&1 | tail -5

# Run migrations in background
python manage.py migrate --noinput &

# Start gunicorn
exec gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile - --error-logfile - --timeout 120
