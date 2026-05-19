#!/bin/sh
set -e

echo "=== KSMS Startup Debug ==="
echo "PORT: $PORT"
echo "DEBUG: $DEBUG"
echo "DB_HOST: $DB_HOST"
echo "ALLOWED_HOSTS: $ALLOWED_HOSTS"
echo "Python: $(which python)"
echo "Gunicorn: $(which gunicorn)"
echo "Working dir: $(pwd)"
echo "========================="

# Test Django settings
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ksms.settings')
import django
django.setup()
print('Django setup: OK')
from django.conf import settings
print(f'DEBUG: {settings.DEBUG}')
print(f'ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}')
print(f'DATABASE: {settings.DATABASES[\"default\"][\"ENGINE\"]}')
" 2>&1 || { echo "Django setup FAILED"; exit 1; }

echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn ksms.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 \
    --log-level info
