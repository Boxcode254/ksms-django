# KSMS Railway → Render Migration — Progress, Problems & Solutions

**Date:** 2026-05-20  
**Project:** Kenya School Management System (KSMS)  
**Repository:** https://github.com/Boxcode254/ksms-django  
**Live URL:** https://ksms-django.onrender.com  

---

## 1. Infrastructure Stack

| Service | Provider | Tier | Cost |
|---|---|---|---|
| Hosting | Render | Free (750 hrs/mo) | $0 |
| Database | Supabase | Free | $0 |
| Email | Resend | Free (100/day) | $0 |
| Redis (Celery) | Render Redis | Free tier | $0 |
| **Total** | | | **$0** |

---

## 2. Migration Progress

### Railway → Render Migration ✅

| Task | Status | Notes |
|---|---|---|
| Created render.yaml | ✅ Done | Blueprint config for web service |
| Updated ALLOWED_HOSTS defaults | ✅ Done | `.onrender.com` with leading dot |
| Removed railway.json | ✅ Done | No longer needed |
| Updated DEPLOYMENT.md | ✅ Done | Render setup instructions added |
| Deployed to Render | ✅ Done | Live at https://ksms-django.onrender.com |
| Health check passing | ✅ Done | `{"status": "ok", "database": "connected"}` |
| Superuser created | ✅ Done | admin.ksms promoted to superuser |

### Day 1 — Accounts & Configuration ✅

| Task | Status | Notes |
|---|---|---|
| Railway account | ✅ Done | Trial expired, migrated to Render |
| Resend email | ✅ Done | API key configured |
| Supabase DB | ✅ Done | Already configured, connection verified |
| Render CLI | ⏳ Pending | Download timing out, using REST API instead |
| Environment variables | ✅ Done | Set via Render dashboard |
| App deployed | ✅ Done | Live at Render URL |

### Day 2 — Superuser & Production Hardening ✅

| Task | Status | Notes |
|---|---|---|
| Migrations run | ✅ Done | Ghost migration fixed manually |
| Superuser created | ✅ Done | admin.ksms promoted via Django shell |
| Ghost migration fixed | ✅ Done | Added old_value/new_value columns to core_auditlog |
| Procfile fixed | ✅ Done | Sequential startup: migrate → collectstatic → ensure_superuser → gunicorn |

### Pending

| Task | Status | Notes |
|---|---|---|
| Test M-Pesa STK push in production | ⏳ Pending | Sandbox configured |
| Test email delivery end-to-end | ⏳ Pending | Resend SMTP configured |
| Celery worker deployment | ⏳ Pending | Need Redis configured |
| Celery beat deployment | ⏳ Pending | Need Redis configured |

---

## 3. Problems Encountered & Solutions Applied

### Problem 1: ALLOWED_HOSTS Wildcard Mismatch
**Root Cause:** Django doesn't support `*.onrender.com` wildcard syntax. It requires a leading dot (`.onrender.com`) for subdomain matching.

**Solution:** Updated `ALLOWED_HOSTS` to `.onrender.com` and `CSRF_TRUSTED_ORIGINS` to `https://.onrender.com`.

---

### Problem 2: Ghost Migration (core_auditlog missing columns)
**Root Cause:** Django's `django_migrations` table recorded migration 0008 as applied, but the actual `ALTER TABLE` commands never executed (likely from an interrupted deploy). This left the `core_auditlog` table missing `old_value` and `new_value` columns. When users logged in, Django tried to write an audit log entry → hit the missing column → 500 error.

**Solution:**
1. Added missing columns (`old_value`, `new_value`) directly to the production `core_auditlog` table
2. Promoted `admin.ksms` to full superuser (`is_staff=True`, `is_superuser=True`, `role=admin`)
3. Fixed the Procfile so future deploys run `migrate → collectstatic → ensure_superuser → gunicorn`

---

### Problem 3: Render CLI Download Timeout
**Root Cause:** GitHub releases download timing out on slow connection.

**Solution:** Using Render REST API directly via `curl` instead of CLI binary.

---

### Problem 4: Railway Trial Expired
**Root Cause:** Railway free trial expired, service would stop.

**Solution:** Migrated to Render free tier (750 hrs/mo). All existing infrastructure (Supabase, Resend, Upstash) reused.

---

## 4. Final Working Configuration

### Dockerfile
```dockerfile
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev libmagic1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip && pip install -r requirements-prod.txt --no-cache-dir

COPY . .
RUN mkdir -p /app/logs /app/media /app/staticfiles
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]
```

### render.yaml
```yaml
services:
  - type: web
    name: ksms-django
    env: docker
    region: oregon
    plan: free
    healthCheckPath: /health/
```

### Procfile
```
web: gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile - --error-logfile - --timeout 120
```

---

## 5. Environment Variables (Render)

> [!CAUTION]
> Never store actual secret values in documentation. See `.env.example` for the full list.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `FIELD_ENCRYPTION_KEY` | Fernet encryption for sensitive fields |
| `DEBUG` | `False` for production |
| `ALLOWED_HOSTS` | `.onrender.com` (leading dot for subdomain matching) |
| `CSRF_TRUSTED_ORIGINS` | `https://.onrender.com` |
| `USE_SQLITE` | `False` — use PostgreSQL |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Supabase PostgreSQL |
| `SECURE_SSL_REDIRECT` | `False` (Render handles HTTPS at edge) |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Resend SMTP |
| `DJANGO_SUPERUSER_USERNAME` | Auto-created superuser username |
| `DJANGO_SUPERUSER_EMAIL` | Auto-created superuser email |
| `DJANGO_SUPERUSER_PASSWORD` | Auto-created superuser password |
| `MPESA_*` | Daraja API configuration |
| `CELERY_BROKER_URL` | Render Redis URL |
| `CELERY_RESULT_BACKEND` | Render Redis URL |

---

## 6. Quick Reference Commands

### Render REST API
```bash
# Set API key
export RENDER_API_KEY=rnd_...

# List services
curl -s https://api.render.com/v1/services -H "Authorization: Bearer $RENDER_API_KEY"

# Get service details
curl -s https://api.render.com/v1/services/exs-d86q9nfavr4c73ecassg -H "Authorization: Bearer $RENDER_API_KEY"

# Trigger deploy
curl -s -X POST https://api.render.com/v1/services/exs-d86q9nfavr4c73ecassg/deploys -H "Authorization: Bearer $RENDER_API_KEY"

# Get deploy logs
curl -s https://api.render.com/v1/services/exs-d86q9nfavr4c73ecassg/deploys -H "Authorization: Bearer $RENDER_API_KEY"
```

### Health Checks
```bash
curl -s https://ksms-django.onrender.com/health/
curl -s -o /dev/null -w "HTTP: %{http_code}\n" https://ksms-django.onrender.com/
```

---

## 7. Lessons Learned

1. **Django ALLOWED_HOSTS requires leading dot** — `.onrender.com` not `*.onrender.com` for subdomain matching
2. **Ghost migrations can occur** — If a deploy is interrupted, `django_migrations` may record a migration as applied when it wasn't
3. **Railway trial expires** — Plan ahead or have a backup hosting option
4. **Render free tier spins down** — After 15 min idle, first request takes ~30s
5. **Render CLI download can timeout** — Use REST API as fallback
6. **Sequential startup is critical** — Migrations must complete before gunicorn starts

---

*Last Updated: 2026-05-20 16:30 EAT*  
*Status: App deployed and operational on Render*
