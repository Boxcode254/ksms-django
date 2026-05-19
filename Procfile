web: gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --access-logfile - --error-logfile -
worker: celery -A ksms worker --loglevel=info --concurrency=2 --queues=high,normal,default
beat: celery -A ksms beat --loglevel=info
