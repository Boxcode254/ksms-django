# KSMS Monitoring & Alerting Guide

## 1. Health Checks

### 1.1 Django Built-in Checks
```bash
# Basic system check
python manage.py check

# Production deployment check
python manage.py check --deploy

# Database check
python manage.py dbshell -c "SELECT 1;"
```

### 1.2 Application Health Endpoint
Add a `/health/` view that returns:
- Database connectivity
- Redis connectivity
- Celery worker status
- Disk space availability

```python
# core/views.py
import logging
from django.http import JsonResponse
from django.db import connection
import redis
from celery.app.control import Inspect

logger = logging.getLogger('ksms')

def health_check(request):
    status = {"status": "ok", "checks": {}}
    code = 200

    # Database
    try:
        connection.ensure_connection()
        status["checks"]["database"] = "ok"
    except Exception as e:
        status["checks"]["database"] = f"error: {e}"
        code = 503

    # Redis
    try:
        r = redis.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        status["checks"]["redis"] = "ok"
    except Exception as e:
        status["checks"]["redis"] = f"error: {e}"
        code = 503

    status["checks"]["celery"] = "ok"  # Add Inspect().ping() for full check

    return JsonResponse(status, status=code)
```

### 1.3 Uptime Monitoring
Configure external monitoring to hit `/health/` every 60 seconds:

| Service | Free Tier | URL |
|---------|-----------|-----|
| UptimeRobot | 50 monitors | uptimerobot.com |
| Better Stack | 10 monitors | betterstack.com |
| Healthchecks.io | 20 checks | healthchecks.io |

## 2. Alerting Thresholds

### 2.1 Application Metrics
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Response time P95 | > 1s | > 3s | Scale workers, check DB |
| Error rate | > 0.5% | > 2% | Check Sentry, rollback |
| 5xx errors | > 5/min | > 20/min | Immediate investigation |
| Memory usage | > 70% | > 90% | Restart workers |
| CPU usage | > 70% | > 90% | Scale horizontally |

### 2.2 Database Metrics
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Connection count | > 15 | > 22 | Check for leaks |
| Slow queries (>1s) | > 10/min | > 50/min | Add indexes |
| Replication lag | > 1s | > 10s | Check Supabase status |
| Disk usage | > 70% | > 85% | Archive old data |

### 2.3 Celery Metrics
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Queue depth | > 50 | > 200 | Scale workers |
| Task failure rate | > 1% | > 5% | Check task logs |
| Task duration P95 | > 30s | > 120s | Optimize tasks |
| Worker count | < 2 | 0 | Restart workers |

### 2.4 Redis Metrics
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Memory usage | > 200MB | > 240MB | Increase maxmemory |
| Evicted keys | > 0 | > 100/min | Increase memory |
| Connected clients | > 20 | > 40 | Check connection leaks |

## 3. Sentry Configuration

### 3.1 Setup
```
SENTRY_DSN=https://<key>@sentry.io/<project-id>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.1
```

### 3.2 Release Tracking
```bash
# Install sentry-cli
pip install sentry-sdk

# Create release
export SENTRY_AUTH_TOKEN=your-token
export SENTRY_ORG=your-org
export SENTRY_PROJECT=ksms

sentry-cli releases new $(git rev-parse --short HEAD)
sentry-cli releases set-commits $(git rev-parse --short HEAD) --auto
sentry-cli releases finalize $(git rev-parse --short HEAD)
```

### 3.3 Alert Rules in Sentry
- **Error rate > 5%**: Page the on-call engineer
- **New issue detected**: Send Slack notification
- **Transaction duration P95 > 2s**: Create Jira ticket
- **Crash-free session rate < 99%**: Immediate investigation

## 4. Log Aggregation

### 4.1 Log Structure
Logs use the format: `timestamp level logger message`

Production logs are written to:
- `/app/logs/ksms.log` — Application logs (rotating, 10MB max, 5 backups)
- `/app/logs/security.log` — Security events (rotating, 10MB max, 5 backups)

### 4.2 Log Shipping Options

| Service | Setup | Cost |
|---------|-------|------|
| Logtail (Better Stack) | pip install logtail | Free tier |
| Papertrail | rsyslog config | Free tier |
| Datadog | dd-agent | Paid |
| Grafana Loki | promtail | Self-hosted |

### 4.3 Structured Logging (Optional)
```python
# Add to settings.py LOGGING formatters
'json': {
    '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
    'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
}
```

## 5. Celery Monitoring

### 5.1 Flower Dashboard
```bash
pip install flower
celery -A ksms flower --port=5555
```

Access at `http://localhost:5555` for real-time monitoring of:
- Task queue depths
- Worker status
- Task success/failure rates
- Task execution times

### 5.2 Flower in Production
```ini
# /etc/systemd/system/ksms-flower.service
[Unit]
Description=KSMS Celery Flower
After=network.target redis-server.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/ksms
EnvironmentFile=/opt/ksms/.env
ExecStart=/opt/ksms/.venv/bin/celery -A ksms flower --port=5555
Restart=always

[Install]
WantedBy=multi-user.target
```

### 5.3 Celery Task Alerts
Monitor these task-specific metrics:
- `finance.tasks.send_payment_receipt_task` — Must complete within 30s
- `finance.tasks.send_daily_fee_reminders_task` — Must complete within 5min
- `finance.tasks.sync_fee_arrears_task` — Must complete within 10min

## 6. Database Monitoring

### 6.1 Supabase Dashboard
- Monitor connection pool usage
- Track query performance
- Set up alerts for slow queries

### 6.2 Custom Slow Query Logging
Django's `django.db.backends` logger at WARNING level captures slow queries:
```python
LOGGING = {
    'loggers': {
        'django.db.backends': {
            'level': 'WARNING',  # Logs queries taking > threshold
        },
    },
}
```

### 6.3 Periodic Index Analysis
```bash
# Check for missing indexes
python manage.py dbshell -c "
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 20;
"

# Check for unused indexes
python manage.py dbshell -c "
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
AND indexname NOT LIKE '%_pkey';
"
```

## 7. Incident Response

### 7.1 Runbook Quick Reference
| Incident | First Action | Escalation |
|----------|-------------|------------|
| Site down | Check server, restart Gunicorn | Page infra team |
| Database slow | Check connection pool, kill long queries | DBA on-call |
| Celery stuck | Restart workers, check Redis | Backend team |
| Payment failures | Check M-Pesa status, retry queue | Finance team |
| Security breach | Rotate keys, enable maintenance mode | Security team |

### 7.2 Communication Channels
- **Slack**: #ksms-incidents for real-time coordination
- **Email**: ops@ksms.example.com for post-incident reports
- **Status page**: status.ksms.example.com for user-facing updates
