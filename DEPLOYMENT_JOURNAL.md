# KSMS Railway Deployment — Progress, Problems & Solutions

**Date:** 2026-05-19  
**Project:** Kenya School Management System (KSMS)  
**Repository:** https://github.com/Boxcode254/ksms-django  
**Live URL:** https://ksms-django-production.up.railway.app  

---

## 1. Infrastructure Stack

| Service | Provider | Tier | Cost |
|---|---|---|---|
| Hosting | Railway | Hobby | ~$5-10/mo |
| Database | Supabase | Free | $0 |
| Email | Resend | Free (100/day) | $0 |
| Redis (Celery) | Upstash | Free (10k/day) | $0 (pending) |
| **Total** | | | **~$5-10/mo** |

---

## 2. Deployment Progress

### Day 1 — Accounts & Configuration ✅

| Task | Status | Notes |
|---|---|---|
| Railway account | ✅ Done | Connected to GitHub repo |
| Resend email | ✅ Done | API key configured |
| Supabase DB | ✅ Done | Already configured, connection verified |
| Railway CLI | ✅ Done | Installed v4.59.0 |
| Environment variables | ✅ Done | 33 vars set via CLI |
| App deployed | ✅ Done | Live at Railway URL |

### Day 2 — Superuser & Production Hardening ✅

| Task | Status | Notes |
|---|---|---|
| Migrations run | ✅ Done | Via entrypoint.sh on container start |
| Superuser created | ✅ Done | Via `ensure_superuser` command + env vars |
| Entrypoint fixed | ✅ Done | Sequential startup: migrate → collectstatic → superuser → gunicorn |

### Pending

| Task | Status | Notes |
|---|---|---|
| Upstash Redis | ⏳ Pending | Required for Celery workers |
| Celery worker deployment | ⏳ Pending | Need Redis first |
| Celery beat deployment | ⏳ Pending | Need Redis first |
| Test M-Pesa STK push in production | ⏳ Pending | Sandbox configured |
| Test email delivery end-to-end | ⏳ Pending | Resend SMTP configured |

---

## 3. Problems Encountered & Solutions Applied

### Problem 1: Build Failed — Missing `requirements.txt`
**Root Cause:** `requirements-prod.txt` includes `-r requirements.txt`, but Dockerfile only copied `requirements-prod.txt`.

**Solution:** Updated Dockerfile to copy both files.

---

### Problem 2: Build Failed — Tailwind Source Files Missing
**Root Cause:** Multi-stage Dockerfile tried to build Tailwind CSS, but pre-built CSS is already committed.

**Solution:** Removed multi-stage build, simplified to single-stage Dockerfile.

---

### Problem 3: Build Failed — `collectstatic` at Build Time
**Root Cause:** Railway injects environment variables at **runtime**, not during Docker build.

**Solution:** Moved `collectstatic` to runtime startup in entrypoint.sh.

---

### Problem 4: Healthcheck Failed — Hardcoded Port 8000
**Root Cause:** Railway assigns a random `PORT` env var. Dockerfile hardcoded `--bind 0.0.0.0:8000`.

**Solution:** Use `$PORT` env var with fallback.

---

### Problem 5: Healthcheck Failed — `SECURE_SSL_REDIRECT=True`
**Root Cause:** Healthcheck requests returned 301 redirects. Railway handles HTTPS at the edge.

**Solution:** Set `SECURE_SSL_REDIRECT=False` in Railway env vars.

---

### Problem 6: Healthcheck Failed — Wrong Path
**Solution:** Changed healthcheck path to `/health/` in `railway.json`.

---

### Problem 7: 500 Error — Missing Static Files
**Root Cause:** WhiteNoise's `CompressedManifestStaticFilesStorage` requires all referenced files to exist.

**Solution:** Run `collectstatic` at startup (after env vars are available).

---

### Problem 8: Race Conditions in Entrypoint
**Root Cause:** Original entrypoint started gunicorn first, then ran migrations and collectstatic in background. This caused race conditions where gunicorn served pages before static files were collected or schema was ready.

**Solution:** Restructured to sequential startup: `migrate → collectstatic → ensure_superuser → gunicorn`. The healthcheck timeout (300s) is generous enough to allow all steps to complete.

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

### railway.json
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE" },
  "deploy": {
    "healthcheckPath": "/health/",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

---

## 5. Environment Variables (Railway)

> [!CAUTION]
> Never store actual secret values in documentation. See `.env.example` for the full list.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `FIELD_ENCRYPTION_KEY` | Fernet encryption for sensitive fields |
| `DEBUG` | `False` for production |
| `USE_SQLITE` | `False` — use PostgreSQL |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Supabase PostgreSQL |
| `ALLOWED_HOSTS` | `*` (Railway handles host validation) |
| `CSRF_TRUSTED_ORIGINS` | Railway app URL |
| `SECURE_SSL_REDIRECT` | `False` (Railway handles HTTPS at edge) |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Resend SMTP |
| `DJANGO_SUPERUSER_USERNAME` | Auto-created superuser username |
| `DJANGO_SUPERUSER_EMAIL` | Auto-created superuser email |
| `DJANGO_SUPERUSER_PASSWORD` | Auto-created superuser password |
| `MPESA_*` | Daraja API configuration |

---

## 6. Quick Reference Commands

### Railway CLI
```bash
# Setup
source "$HOME/.railway/env"

# Check status
railway status

# View logs
railway logs --latest --lines 50

# Deploy
railway up --service ksms-django --detach

# Set variables (example)
railway variables set DJANGO_SUPERUSER_USERNAME='admin.ksms'
railway variables set DJANGO_SUPERUSER_EMAIL='admin@example.com'
railway variables set DJANGO_SUPERUSER_PASSWORD='YourSecurePassword'
```

### Git Commands
```bash
# Trigger Railway deploy
git add -A && git commit -m "fix: description" && git push origin main
```

### Health Checks
```bash
curl -s https://ksms-django-production.up.railway.app/health/
curl -s -o /dev/null -w "HTTP: %{http_code}\n" https://ksms-django-production.up.railway.app/
```

---

## 7. Lessons Learned

1. **Railway injects env vars at runtime, not build time** — Never run Django commands in Dockerfile `RUN` steps.
2. **Railway assigns random PORT** — Always use `$PORT` env var, never hardcode ports.
3. **`SECURE_SSL_REDIRECT` breaks healthchecks** — Set to `False` behind Railway's HTTPS termination.
4. **`collectstatic` must run after env vars are available** — Move to entrypoint, not Dockerfile RUN.
5. **Sequential startup beats backgrounded tasks** — Race conditions cause intermittent 500 errors.
6. **GitHub webhook required for auto-deploys** — Connect repo in Railway dashboard.
7. **WhiteNoise needs all static files** — `CompressedManifestStaticFilesStorage` fails if any referenced file is missing.

---

*Last Updated: 2026-05-20 12:58 EAT*  
*Status: App deployed and operational*
