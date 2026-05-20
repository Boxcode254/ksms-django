#!/bin/sh
# Start gunicorn in background
gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile - --error-logfile - --timeout 120 &
GUNICORN_PID=$!

# Run migrations in background
python manage.py migrate --noinput &

# Run collectstatic in background
python manage.py collectstatic --noinput &

# Wait for gunicorn
wait $GUNICORN_PID
