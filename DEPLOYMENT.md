# KSMS Deployment Runbook

Production deployment guide for Kenya School Management System targeting 100k users.

## Architecture Overview

```
                    ┌─────────────┐
   Browser ────────► │  Gunicorn   │
                     │  (WSGI)     │
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │   Django    │
                     │  + HTMX     │
                     └──┬───┬───┬─┘
                        │   │   │
               ┌────────┘   │   └─────────┐
               ▼            ▼             ▼
         ┌──────────┐ ┌─────────┐  ┌────────────┐
         │ Supabase │ │  Redis  │  │ WhiteNoise │
         │ Postgres │ │ (Celery)│  │ (statics)  │
         └──────────┘ └─────────┘  └────────────┘
```

## 0. Render Deployment (Recommended)

### 0.1 One-Click Deploy via Blueprint

1. Go to [Render Dashboard](https://dashboard.render.com) → **Blueprints** → **New Blueprint Instance**
2. Connect your GitHub repo (`Boxcode254/ksms-django`)
3. Render reads `render.yaml` and creates the web service automatically

### 0.2 Manual Setup via Dashboard

1. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Configure:
   - **Build Command:** Leave blank (Docker auto-detected)
   - **Start Command:** Leave blank (uses Dockerfile CMD)
   - **Environment:** Docker
   - **Region:** Oregon (closest to Supabase US regions)
4. Set all environment variables (see `.env.example`)
5. Click **Create Web Service**

### 0.3 Required Environment Variables

Set these in Render Dashboard → your service → **Environment**:

| Variable | Value |
|---|---|
| `SECRET_KEY` | Generate a new random key |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `yourapp.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://yourapp.onrender.com` |
| `USE_SQLITE` | `False` |
| `DB_NAME` | `postgres` |
| `DB_USER` | `postgres.<project-ref>` |
| `DB_PASSWORD` | `<supabase-password>` |
| `DB_HOST` | `aws-0-<region>.pooler.supabase.com` |
| `DB_PORT` | `5432` |
| `CONN_MAX_AGE` | `60` |
| `CONN_HEALTH_CHECKS` | `True` |
| `SECURE_SSL_REDIRECT` | `False` (Render handles HTTPS) |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `SECURE_HSTS_SECONDS` | `31536000` |
| `FIELD_ENCRYPTION_KEY` | `<fernet-key>` |
| `EMAIL_HOST_PASSWORD` | `<resend-api-key>` |
| `DJANGO_SUPERUSER_USERNAME` | `admin.ksms` |
| `DJANGO_SUPERUSER_EMAIL` | `admin@ksms.local` |
| `DJANGO_SUPERUSER_PASSWORD` | `<strong-password>` |
| `CELERY_BROKER_URL` | `<upstash-redis-url>` |
| `CELERY_RESULT_BACKEND` | `<upstash-redis-url>` |

### 0.4 Post-Deploy Verification

```bash
# Health check
curl -s https://yourapp.onrender.com/health/

# Expected: {"status": "ok", "database": "connected"}

# Login at:
# https://yourapp.onrender.com/accounts/login/
```

> [!NOTE]
> Render free tier spins down after 15 minutes of inactivity. First request after spin-down takes ~30s. Upgrade to $7/mo for always-on.

---

## 1. Supabase PostgreSQL Setup

### 1.1 Create Project
1. Go to https://supabase.com and create a new project
2. Note the project reference ID (e.g., `rmfkykcijcndwvsursmu`)
3. Go to Project Settings → Database → Connection string

### 1.2 Connection Strings
Use the **Transaction** (PgBouncer) port for Django:
```
DB_HOST=aws-0-eu-west-1.pooler.supabase.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres.<project-ref>
DB_PASSWORD=<your-password>
```

For direct connections (migrations, one-off scripts), use port 6543.

### 1.3 Database Configuration
- Enable connection pooling (PgBouncer is automatic on Supabase)
- Set `CONN_MAX_AGE=60` and `CONN_HEALTH_CHECKS=True` in Django settings
- Recommended pool size: 15-25 connections for 100k users

### 1.4 Backups
Supabase provides automatic daily backups with 7-day retention.
See `docs/ops/automated-backups.md` for additional backup strategies.

## 2. Redis Setup

### 2.1 Managed Redis (Recommended)
Use Supabase Redis, Upstash, or Redis Cloud:
```
CELERY_BROKER_URL=rediss://default:<password>@<host>:<port>/0
CELERY_RESULT_BACKEND=rediss://default:<password>@<host>:<port>/0
```

### 2.2 Self-Hosted Redis
```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl enable redis-server

# Verify
redis-cli ping  # Should return PONG
```

### 2.3 Redis Configuration for Production
```
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
```

## 3. Celery Deployment

### 3.1 Worker Processes
For 100k users, run multiple workers:
```bash
# Main worker (all queues)
celery -A ksms worker --loglevel=info --concurrency=4 --queues=default,normal,high,low --hostname=worker1@%h

# Dedicated high-priority worker
celery -A ksms worker --loglevel=info --concurrency=2 --queues=high --hostname=high-worker@%h
```

### 3.2 Celery Beat (Scheduler)
```bash
celery -A ksms beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### 3.3 Systemd Services
```ini
# /etc/systemd/system/ksms-celery-worker.service
[Unit]
Description=KSMS Celery Worker
After=network.target redis-server.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/ksms
EnvironmentFile=/opt/ksms/.env
ExecStart=/opt/ksms/.venv/bin/celery -A ksms worker --loglevel=info --concurrency=4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/ksms-celery-beat.service
[Unit]
Description=KSMS Celery Beat
After=network.target redis-server.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/ksms
EnvironmentFile=/opt/ksms/.env
ExecStart=/opt/ksms/.venv/bin/celery -A ksms beat --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 4. Domain & DNS

### 4.1 DNS Records
```
Type    Name        Value               TTL
A       @           <server-ip>         300
A       www         <server-ip>         300
CNAME   cdn         <cdn-provider>      3600
MX      @           mail.provider.com   3600
TXT     @           v=spf1 ...          3600
```

### 4.2 ALLOWED_HOSTS
```
ALLOWED_HOSTS=ksms.example.com,www.ksms.example.com
CSRF_TRUSTED_ORIGINS=https://ksms.example.com,https://www.ksms.example.com
```

## 5. SSL/TLS

### 5.1 Let's Encrypt with Certbot
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d ksms.example.com -d www.ksms.example.com

# Auto-renewal (already configured by certbot)
sudo certbot renew --dry-run
```

### 5.2 Django SSL Settings
```
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

## 6. Static Files

### 6.1 Collect Static
```bash
python manage.py collectstatic --noinput
```

### 6.2 WhiteNoise
WhiteNoise serves compressed static files directly from Django. No separate web server needed for statics.

### 6.3 CDN (Optional)
Set `CDN_STATIC_URL` to your CDN endpoint:
```
CDN_STATIC_URL=https://cdn.example.com/static/
```

## 7. Database Migrations

### 7.1 Deploy Migrations
```bash
# Always run before deploying new code
python manage.py migrate --noinput

# Verify
python manage.py showmigrations
```

### 7.2 Zero-Downtime Migrations
- Add fields with `null=True` first, then backfill, then add constraints
- Never drop columns in the same deploy that removes their usage
- Use `RunPython` migrations for data migrations

## 8. Deployment Checklist

### Render (Docker)
- [ ] Connect GitHub repo to Render
- [ ] Set all environment variables in Render dashboard
- [ ] Deploy (auto-triggers on push to main)
- [ ] Verify health endpoint: `curl https://yourapp.onrender.com/health/`
- [ ] Check logs in Render dashboard
- [ ] Login with superuser credentials

### Self-Hosted (VPS)
- [ ] Pull latest code
- [ ] Activate virtual environment
- [ ] Install dependencies: `pip install -r requirements-prod.txt`
- [ ] Run migrations: `python manage.py migrate --noinput`
- [ ] Collect static: `python manage.py collectstatic --noinput`
- [ ] Build Tailwind: `python manage.py tailwind build`
- [ ] Run checks: `python manage.py check --deploy`
- [ ] Restart Gunicorn: `sudo systemctl restart ksms`
- [ ] Restart Celery workers: `sudo systemctl restart ksms-celery-worker`
- [ ] Restart Celery beat: `sudo systemctl restart ksms-celery-beat`
- [ ] Verify health endpoint: `curl https://ksms.example.com/health/`
- [ ] Check logs: `journalctl -u ksms -n 50 --no-pager`

## 9. Rollback Procedure

### 9.1 Render Rollback
1. Go to Render Dashboard → your service → **Events**
2. Find the last known-good deployment
3. Click **Rollback**
4. Wait for the rollback to complete (~2 minutes)

### 9.2 Code Rollback
```bash
# Find the last good commit
git log --oneline -10

# Checkout and redeploy
git checkout <good-commit-hash>
pip install -r requirements-prod.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart ksms ksms-celery-worker ksms-celery-beat
```

### 9.3 Database Rollback
```bash
# Check migration history
python manage.py showmigrations

# Rollback specific app
python manage.py migrate <app> <previous_migration>

# WARNING: Only rollback if the migration is reversible
# Always backup before rolling back
```

### 9.4 Supabase Point-in-Time Recovery
1. Go to Supabase Dashboard → Database → Backups
2. Select the backup before the problematic migration
3. Restore to a new branch for testing first

## 10. Gunicorn Configuration

```python
# gunicorn.conf.py
bind = "0.0.0.0:8000"
workers = 4  # (2 * CPU cores) + 1
worker_class = "sync"
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
```

```ini
# /etc/systemd/system/ksms.service
[Unit]
Description=KSMS Gunicorn
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/ksms
EnvironmentFile=/opt/ksms/.env
ExecStart=/opt/ksms/.venv/bin/gunicorn ksms.wsgi:application --config gunicorn.conf.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 11. Performance Targets for 100k Users

| Metric | Target |
|--------|--------|
| Page load (P95) | < 2s |
| API response (P95) | < 500ms |
| Database connections | < 25 |
| Redis memory | < 256MB |
| Celery queue depth | < 100 |
| Error rate | < 0.1% |
