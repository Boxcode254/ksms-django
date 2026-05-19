#!/bin/sh
set -e

echo "=== KSMS Startup ==="
echo "PORT: $PORT"
echo "DEBUG: $DEBUG"
echo "DB_HOST: $DB_HOST"
echo "ALLOWED_HOSTS: $ALLOWED_HOSTS"
echo "Python: $(which python)"
echo "Gunicorn: $(which gunicorn)"
echo "Working dir: $(pwd)"
echo "===================="

# Test Django settings
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ksms.settings')
import django
django.setup()
print('Django setup: OK')
print(f'DEBUG: {os.environ.get(\"DEBUG\", \"not set\")}')
print(f'DB_HOST: {os.environ.get(\"DB_HOST\", \"not set\")}')
print(f'ALLOWED_HOSTS: {os.environ.get(\"ALLOWED_HOSTS\", \"not set\")}')
" 2>&1 || echo "Django setup FAILED"

echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn ksms.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 4 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 \
    --log-level info
