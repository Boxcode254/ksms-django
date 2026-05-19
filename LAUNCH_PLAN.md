# KSMS 6-Day Launch Plan

**Target Launch:** 6 days from today  
**Current Status:** Code complete (9.9/10 production readiness)  
**Database:** Supabase free tier  
**Hosting:** Railway (recommended)  
**Email:** Resend (recommended)  

---

## Recommended Stack

### Hosting: Railway
- **URL:** https://railway.app
- **Cost:** $5 free credit, then ~$5-10/mo
- **Why:** Auto-detects Django, native Redis add-on, Celery support, `railway up` deploys in 2 min
- **Free URL:** `yourapp.up.railway.app` (no domain needed)

### Email: Resend
- **URL:** https://resend.com
- **Cost:** 100 emails/day free, then $0.20/1k
- **Why:** 5 min setup, no domain verification for sandbox, excellent deliverability

### Database: Supabase (existing)
- **Tier:** Free (500 MB, 2 projects)
- **Connection:** Use PgBouncer connection string for pooling

### Redis: Upstash
- **URL:** https://upstash.com
- **Cost:** Free tier (10k commands/day)
- **Why:** Serverless Redis, works with Railway, zero ops

---

## Day 1: Accounts & Infrastructure

**Goal:** All external services created and verified.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Create Railway account | Connect GitHub repo, enable auto-deploy | ☐ |
| 2 | Create Resend account | Get API key, note SMTP credentials | ☐ |
| 3 | Create Upstash Redis | Free tier, copy `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` | ☐ |
| 4 | Verify Supabase connection | Test connection string with `psql` or Django shell | ☐ |
| 5 | Generate Railway config files | `railway.json`, `Procfile` (see below) | ☐ |

### Verification Commands
```bash
# Test Supabase connection
.venv/bin/python -c "
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ksms.settings'
os.environ['USE_SQLITE'] = 'False'
import django; django.setup()
from django.db import connection
connection.ensure_connection()
print('Supabase connection OK')
"

# Test Resend SMTP (after setup)
.venv/bin/python -c "
import smtplib
from email.message import EmailMessage
msg = EmailMessage()
msg['Subject'] = 'Test'
msg['From'] = 'onboarding@resend.dev'
msg['To'] = 'your-email@example.com'
msg.set_content('Hello from KSMS')
# Use Resend SMTP credentials here
"
```

---

## Day 2: Railway Deployment

**Goal:** App running in production mode on Railway.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Add Railway services | Django web, Celery worker, Celery beat | ☐ |
| 2 | Configure env vars | All variables from `.env.example` | ☐ |
| 3 | Add Upstash Redis | External connection via Railway dashboard | ☐ |
| 4 | Deploy | `railway up` or push to GitHub | ☐ |
| 5 | Verify `/health/` | Returns `{"status": "ok", "database": "connected"}` | ☐ |
| 6 | Run migrations | `railway run python manage.py migrate` | ☐ |
| 7 | Create superuser | `railway run python manage.py createsuperuser` | ☐ |

### Required Railway Environment Variables
```
# Core
SECRET_KEY=<generate-new-random-key>
DEBUG=False
ALLOWED_HOSTS=yourapp.up.railway.app
CSRF_TRUSTED_ORIGINS=https://yourapp.up.railway.app

# Database (from Supabase)
USE_SQLITE=False
DB_NAME=postgres
DB_USER=postgres.yourprojectref
DB_PASSWORD=<supabase-password>
DB_HOST=aws-0-your-region.pooler.supabase.com
DB_PORT=5432
CONN_MAX_AGE=60
CONN_HEALTH_CHECKS=True

# Redis (from Upstash)
CELERY_BROKER_URL=<upstash-redis-url>
CELERY_RESULT_BACKEND=<upstash-redis-url>

# Email (from Resend)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=onboarding@resend.dev
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=<resend-api-key>

# Security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
FIELD_ENCRYPTION_KEY=<generate-fernet-key>

# Feature toggles
MPESA_STK_ENABLED=True
AUTO_REMINDERS_ENABLED=True
SEND_PAYMENT_NOTIFICATIONS=True
```

### Railway Config Files

**`railway.json`** (create in root):
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --access-logfile - --error-logfile -",
    "healthcheckPath": "/health/",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**`Procfile`** (create in root):
```
web: gunicorn ksms.wsgi:application --bind 0.0.0.0:$PORT --workers 4
worker: celery -A ksms worker --loglevel=info --concurrency=2
beat: celery -A ksms beat --loglevel=info
```

---

## Day 3: Email & M-Pesa Integration

**Goal:** Transactional emails working, payment flow tested.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Configure Resend SMTP | Add email settings to Railway env vars | ☐ |
| 2 | Send test email | Use Django shell or create test invoice | ☐ |
| 3 | Verify payment receipt email | Trigger payment, check inbox | ☐ |
| 4 | Verify fee reminder email | Trigger reminder, check inbox | ☐ |
| 5 | Test M-Pesa STK push | Use sandbox or production credentials | ☐ |
| 6 | Test M-Pesa callback | Verify payment status updates | ☐ |

### Test Commands
```bash
# Send test email via Django shell
.venv/bin/python manage.py shell -c "
from django.core.mail import send_mail
send_mail(
    'KSMS Test',
    'This is a test email from KSMS.',
    'onboarding@resend.dev',
    ['your-email@example.com'],
    fail_silently=False,
)
print('Test email sent')
"
```

---

## Day 4: Data & User Setup

**Goal:** Production database seeded, all roles tested.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Run migrations | `railway run python manage.py migrate` | ☐ |
| 2 | Create superuser | `railway run python manage.py createsuperuser` | ☐ |
| 3 | Create school | Via Django admin or management command | ☐ |
| 4 | Create academic year + terms | Via Django admin | ☐ |
| 5 | Seed demo data | 1 teacher, 5 students, 2 guardians, 3 classes | ☐ |
| 6 | Test admin role | Login, view dashboard, create invoice | ☐ |
| 7 | Test teacher role | Login, view classes, mark attendance | ☐ |
| 8 | Test student role | Login, view grades, download report card | ☐ |
| 9 | Test parent role | Login, view children, pay invoice | ☐ |

### Seed Command (create if needed)
```bash
# Create a management command to seed demo data
.venv/bin/python manage.py seed_demo_data
```

---

## Day 5: Testing & Hardening

**Goal:** Production-ready, no known issues.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Run `check --deploy` | `railway run python manage.py check --deploy` | ☐ |
| 2 | Manual smoke test | Login → create invoice → send STK → view report | ☐ |
| 3 | Verify `DEBUG=False` | No sensitive data in errors, no debug toolbar | ☐ |
| 4 | Test backup download | Download school backup, verify file | ☐ |
| 5 | Test soft delete | Delete student, verify it's hidden but recoverable | ☐ |
| 6 | Test rate limiting | Spam login, verify 429 response | ☐ |
| 7 | Check logs | Railway dashboard, verify no errors | ☐ |
| 8 | Set up Sentry (optional) | Add `SENTRY_DSN` to Railway env vars | ☐ |

### Verification Commands
```bash
# Run deploy check
railway run python manage.py check --deploy

# Test rate limiting
curl -X POST https://yourapp.up.railway.app/accounts/login/ \
  -d "username=test&password=wrong" \
  -v 2>&1 | grep -E "HTTP/|X-RateLimit"
```

---

## Day 6: Launch

**Goal:** Go live, monitor, document.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Final health check | `/health/` returns 200 | ☐ |
| 2 | Share URL with team | `https://yourapp.up.railway.app` | ☐ |
| 3 | Monitor Railway logs | Watch for errors in first hour | ☐ |
| 4 | Monitor Resend dashboard | Check delivery rates, bounces | ☐ |
| 5 | Test M-Pesa production | Real transaction (KES 1) | ☐ |
| 6 | Document known issues | Create GitHub issues for post-launch fixes | ☐ |
| 7 | Celebrate 🎉 | You're live! | ☐ |

### Post-Launch Monitoring
- **Railway:** Deploy logs, resource usage, restart count
- **Supabase:** Database connections, query performance, storage
- **Upstash:** Redis command count, memory usage
- **Resend:** Email delivery rate, bounce rate, spam complaints

---

## Rollback Plan

If something goes wrong:

| Scenario | Action |
|---|---|
| App crashes on deploy | `railway rollback` to previous deployment |
| Database migration fails | `railway run python manage.py migrate --fake` then fix |
| Email not working | Revert `EMAIL_BACKEND` to console, fix SMTP later |
| M-Pesa failing | Set `MPESA_STK_ENABLED=False`, investigate |
| Performance issues | Scale Railway workers, add Redis caching |

---

## Cost Estimate (Monthly)

| Service | Tier | Cost |
|---|---|---|
| Railway | Hobby | ~$5-10 |
| Supabase | Free | $0 |
| Upstash Redis | Free | $0 |
| Resend | Free (100/day) | $0 |
| **Total** | | **~$5-10/mo** |

At 100k users across 200 schools, costs will scale to ~$50-100/mo.

---

## Quick Reference

| What | URL/Command |
|---|---|
| Railway Dashboard | https://railway.app/dashboard |
| Resend Dashboard | https://resend.com/dashboard |
| Upstash Console | https://console.upstash.com |
| Supabase Dashboard | https://supabase.com/dashboard |
| Health Check | `https://yourapp.up.railway.app/health/` |
| Django Admin | `https://yourapp.up.railway.app/admin/` |
| Deploy Command | `railway up` |
| Run Management Command | `railway run python manage.py <command>` |
| View Logs | `railway logs` |

---

*Generated: 2026-05-19 | Last Updated: 2026-05-19*
