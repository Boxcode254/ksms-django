# KSMS 6-Day Launch Plan

**Target Launch:** 6 days from today  
**Current Status:** Code complete, deployed to Render  
**Database:** Supabase (PostgreSQL)  
**Hosting:** Render (Free tier, 750 hrs/mo)  
**Email:** Resend (100/day free)  
**Redis:** Render Redis (free tier)  

---

## Recommended Stack

### Hosting: Render
- **URL:** https://render.com
- **Cost:** Free tier (750 hrs/mo), $7/mo for always-on
- **Why:** Docker-native, Blueprint support, easy env var management
- **Free URL:** `yourapp.onrender.com`

### Email: Resend
- **URL:** https://resend.com
- **Cost:** 100 emails/day free, then $0.20/1k
- **Why:** 5 min setup, no domain verification for sandbox, excellent deliverability

### Database: Supabase (existing)
- **Tier:** Free (500 MB, 2 projects)
- **Connection:** Use PgBouncer connection string for pooling

### Redis: Render Redis
- **Cost:** Free tier available
- **Why:** Native Render integration, zero ops

---

## Day 1: Accounts & Infrastructure ✅

**Goal:** All external services created and verified.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Render account | Connect GitHub repo, deploy via Blueprint | ✅ Done |
| 2 | Resend account | Get API key, note SMTP credentials | ✅ Done |
| 3 | Render Redis | Free tier, copy URL | ✅ Done |
| 4 | Verify Supabase connection | Test connection string with Django shell | ✅ Done |
| 5 | Generate Render config | `render.yaml` (committed to repo) | ✅ Done |

### Verification Commands
```bash
# Test Supabase connection
.venv/bin/python -c "
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ksms.settings'
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

## Day 2: Render Deployment ✅

**Goal:** App running in production mode on Render.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Deploy via Blueprint | `render.yaml` auto-creates web service | ✅ Done |
| 2 | Configure env vars | All variables set in Render dashboard | ✅ Done |
| 3 | Add Render Redis | Connected via env vars | ✅ Done |
| 4 | Deploy | Auto-triggers on push to main | ✅ Done |
| 5 | Verify `/health/` | Returns `{"status": "ok", "database": "connected"}` | ✅ Done |
| 6 | Run migrations | Via entrypoint.sh on container start | ✅ Done |
| 7 | Create superuser | Via `ensure_superuser` command + env vars | ✅ Done |

### Required Render Environment Variables
```
# Core
SECRET_KEY=<generate-new-random-key>
DEBUG=False
ALLOWED_HOSTS=.onrender.com
CSRF_TRUSTED_ORIGINS=https://.onrender.com

# Database (from Supabase)
USE_SQLITE=False
DB_NAME=postgres
DB_USER=postgres.yourprojectref
DB_PASSWORD=<supabase-password>
DB_HOST=aws-0-your-region.pooler.supabase.com
DB_PORT=5432
CONN_MAX_AGE=60
CONN_HEALTH_CHECKS=True

# Redis (from Render Redis)
CELERY_BROKER_URL=<render-redis-url>
CELERY_RESULT_BACKEND=<render-redis-url>

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

# Superuser (auto-created on startup)
DJANGO_SUPERUSER_USERNAME=admin.ksms
DJANGO_SUPERUSER_EMAIL=admin@ksms.local
DJANGO_SUPERUSER_PASSWORD=<strong-password>

# Feature toggles
MPESA_STK_ENABLED=True
AUTO_REMINDERS_ENABLED=True
SEND_PAYMENT_NOTIFICATIONS=True
```

### Render Config Files

**`render.yaml`** (in repo root):
```yaml
services:
  - type: web
    name: ksms-django
    env: docker
    region: oregon
    plan: free
    healthCheckPath: /health/
```

---

## Day 3: Email & M-Pesa Integration

**Goal:** Transactional emails working, payment flow tested.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Configure Resend SMTP | Add email settings to Render env vars | ⏳ Pending |
| 2 | Send test email | Use Django shell or create test invoice | ⏳ Pending |
| 3 | Verify payment receipt email | Trigger payment, check inbox | ⏳ Pending |
| 4 | Verify fee reminder email | Trigger reminder, check inbox | ⏳ Pending |
| 5 | Test M-Pesa STK push | Use sandbox or production credentials | ⏳ Pending |
| 6 | Test M-Pesa callback | Verify payment status updates | ⏳ Pending |

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

## Day 4: Data & User Setup ✅

**Goal:** Production database seeded, all roles tested.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Run migrations | Via entrypoint.sh on container start | ✅ Done |
| 2 | Create superuser | Via `ensure_superuser` command | ✅ Done |
| 3 | Create school | Springs Of Life Academy via `seed_phase2_demo` | ✅ Done |
| 4 | Create academic year + terms | Via seed command | ✅ Done |
| 5 | Seed demo data | 2 teachers, 2 students, 2 guardians, grades, payments | ✅ Done |
| 6 | Test admin role | Login, view dashboard, verify data | ✅ Done |
| 7 | Test teacher role | Login, view classes, verify assignments | ✅ Done |
| 8 | Test student role | Login, view grades, verify report card | ✅ Done |
| 9 | Test parent role | Login, view children, verify invoices | ✅ Done |

### Seed Command
```bash
python manage.py seed_phase2_demo
python manage.py sync_demo_accounts
```

---

## Day 5: Testing & Hardening ✅

**Goal:** Production-ready, no known issues.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Run `check --deploy` | 0 issues with production env values | ✅ Done |
| 2 | Full test suite | 258 tests, 0 failures | ✅ Done |
| 3 | Verify `DEBUG=False` | No sensitive data in errors, clean 404 page | ✅ Done |
| 4 | Security headers audit | HSTS, CSP, X-Frame-Options all correct | ✅ Done |
| 5 | HTTP→HTTPS redirect | `http://` returns 301 → `https://` | ✅ Done |
| 6 | Test rate limiting | CSRF gate blocks brute-force; rate limiter in allauth adapter | ✅ Verified |
| 7 | CSP fix deployed | Added `https://unpkg.com` to script-src | ✅ Done |
| 8 | SSL redirect fix | Changed `SECURE_SSL_REDIRECT` from False to True | ✅ Done |

### Verification Commands
```bash
# Run deploy check (via Render ephemeral shell)
render ssh ksms-django -e -- python manage.py check --deploy

# Test rate limiting
curl -X POST https://ksms-django.onrender.com/accounts/login/ \
  -d "username=test&password=wrong" \
  -v 2>&1 | grep -E "HTTP/|X-RateLimit"
```

---

## Day 6: Launch

**Goal:** Go live, monitor, document.

| # | Task | Details | Status |
|---|---|---|---|
| 1 | Final health check | `/health/` returns 200 | ⏳ Pending |
| 2 | Share URL with team | `https://ksms-django.onrender.com` | ⏳ Pending |
| 3 | Monitor Render logs | Watch for errors in first hour | ⏳ Pending |
| 4 | Monitor Resend dashboard | Check delivery rates, bounces | ⏳ Pending |
| 5 | Test M-Pesa production | Real transaction (KES 1) | ⏳ Pending |
| 6 | Document known issues | Create GitHub issues for post-launch fixes | ⏳ Pending |
| 7 | Celebrate | You're live! | ⏳ Pending |

### Post-Launch Monitoring
- **Render:** Deploy logs, resource usage, restart count
- **Supabase:** Database connections, query performance, storage
- **Render Redis:** Memory usage, command count
- **Resend:** Email delivery rate, bounce rate, spam complaints

---

## Rollback Plan

If something goes wrong:

| Scenario | Action |
|---|---|
| App crashes on deploy | Render Dashboard → Events → Rollback to previous deploy |
| Database migration fails | `render ssh ksms-django -e -- python manage.py migrate --fake` then fix |
| Email not working | Revert `EMAIL_BACKEND` to console, fix SMTP later |
| M-Pesa failing | Set `MPESA_STK_ENABLED=False`, investigate |
| Performance issues | Upgrade Render plan, add Redis caching |

---

## Cost Estimate (Monthly)

| Service | Tier | Cost |
|---|---|---|
| Render | Free (750 hrs) | $0 |
| Render (always-on) | Starter | $7/mo |
| Supabase | Free | $0 |
| Render Redis | Free | $0 |
| Resend | Free (100/day) | $0 |
| **Total** | | **$0 - $7/mo** |

At 100k users across 200 schools, costs will scale to ~$50-100/mo.

---

## Quick Reference

| What | URL/Command |
|---|---|
| Render Dashboard | https://dashboard.render.com |
| Resend Dashboard | https://resend.com/dashboard |
| Supabase Dashboard | https://supabase.com/dashboard |
| Health Check | `https://ksms-django.onrender.com/health/` |
| Django Admin | `https://ksms-django.onrender.com/admin/` |
| Deploy Command | `render deploys create <service-id>` |
| Run Management Command | `render ssh <service-id> -e -- python manage.py <command>` |
| View Logs | Render Dashboard → Events → Logs |

---

*Generated: 2026-05-19 | Last Updated: 2026-05-20*
