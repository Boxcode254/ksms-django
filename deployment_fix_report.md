# KSMS Deployment Fix Report

**Date:** 2026-05-20 12:58 EAT

## Current State (Verified)

| Component | Status |
|---|---|
| Health check (`/health/`) | ✅ `{"status": "ok", "database": "connected"}` |
| Landing page | ✅ Renders with full CSS |
| Login page | ✅ Staff login form working |
| Static files | ✅ Served via WhiteNoise |
| Database | ✅ Connected to Supabase PostgreSQL |
| Superuser | ❌ Not created yet |
| Migrations (production) | ⚠️ May be stale — entrypoint was backgrounding them |
| Railway API token | ❌ Expired/revoked — CLI cannot set env vars |

---

## Fixes Applied (Code Pushed to `main`)

### 1. New Management Command: `ensure_superuser`
**File:** [ensure_superuser.py](file:///home/natasha/Documents/MY%20PROJECTS/Website%20Projects/Django%20-%20School%20MS/core/management/commands/ensure_superuser.py)

- Reads `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` from env
- Creates superuser only if it doesn't exist (idempotent — safe on every container restart)
- Marks email as verified in allauth (no confirmation round-trip needed)
- Gracefully skips if env vars are not set

### 2. Fixed Entrypoint (Race Condition Fix)
**File:** [entrypoint.sh](file:///home/natasha/Documents/MY%20PROJECTS/Website%20Projects/Django%20-%20School%20MS/entrypoint.sh)

**Before (broken):** Gunicorn started first, migrations/collectstatic ran in background → race conditions, stale schema, missing static files.

**After (fixed):** Sequential startup:
```
[1/4] migrate → [2/4] collectstatic → [3/4] ensure_superuser → [4/4] gunicorn (exec)
```

### 3. Removed Vercel Analytics (404 Fix)
**File:** [base.html](file:///home/natasha/Documents/MY%20PROJECTS/Website%20Projects/Django%20-%20School%20MS/templates/base.html)

Removed `/_vercel/insights/script.js` reference causing 404 on every page load. App is on Railway, not Vercel.

### 4. Redacted Secrets from Documentation (Security Fix)
**File:** [DEPLOYMENT_JOURNAL.md](file:///home/natasha/Documents/MY%20PROJECTS/Website%20Projects/Django%20-%20School%20MS/DEPLOYMENT_JOURNAL.md)

> [!CAUTION]
> The previous version of `DEPLOYMENT_JOURNAL.md` contained live API keys, database passwords, Railway tokens, and Resend API keys in plaintext. These have been scrubbed.

All credential values replaced with env var names and placeholder references.

---

## Manual Steps Required

> [!IMPORTANT]
> The Railway API token has expired. You must complete these steps manually via the Railway dashboard.

### Step 1: Generate a New Railway API Token
1. Go to [Railway Dashboard → Account Settings → Tokens](https://railway.app/account/tokens)
2. Generate a new token
3. Update your local env: `export RAILWAY_TOKEN="<new-token>"`

### Step 2: Set Superuser Environment Variables
In Railway Dashboard → **Djano-KSMS** project → **ksms-django** service → **Variables**:

| Variable | Value |
|---|---|
| `DJANGO_SUPERUSER_USERNAME` | `admin.ksms` |
| `DJANGO_SUPERUSER_EMAIL` | `admin@ksms.local` |
| `DJANGO_SUPERUSER_PASSWORD` | *(choose a strong password — min 12 chars, mixed case, numbers, special chars)* |

> [!TIP]
> After adding these variables, Railway will automatically redeploy. The new entrypoint will run migrations, collect static files, create the superuser, then start gunicorn.

### Step 3: Verify Deployment
After the new deploy completes:

```bash
# Check health
curl -s https://ksms-django-production.up.railway.app/health/

# Try logging in with the superuser credentials at:
# https://ksms-django-production.up.railway.app/accounts/login/
```

### Step 4: Login Test
Go to [https://ksms-django-production.up.railway.app/accounts/login/](https://ksms-django-production.up.railway.app/accounts/login/) and sign in with:
- Username: `admin.ksms`
- Password: *(the password you set in Step 2)*

---

## Files Changed

| File | Change |
|---|---|
| `core/management/commands/ensure_superuser.py` | **New** — idempotent superuser creation from env vars |
| `entrypoint.sh` | **Rewritten** — sequential startup, `exec gunicorn` for proper PID 1 |
| `start.sh` | **Rewritten** — synchronized with entrypoint.sh |
| `templates/base.html` | **Edited** — removed Vercel analytics script |
| `DEPLOYMENT_JOURNAL.md` | **Rewritten** — redacted all live secrets |
| `.env.example` | **Edited** — added `DJANGO_SUPERUSER_*` vars |

---

*Commit: `4e8a76a` — pushed to `main`, Railway auto-deploy should be triggered.*
