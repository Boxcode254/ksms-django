#!/usr/bin/env bash
# =============================================================================
# KSMS Day 1 Setup Validation Script
# Run this after creating Railway, Resend, and Upstash accounts.
# Usage: bash setup_day1.sh
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo " KSMS Day 1 Setup Validation"
echo "=========================================="
echo ""

PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo -e "  ${GREEN}✓${NC} $name"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗${NC} $name"
        FAIL=$((FAIL + 1))
    fi
}

# ─── 1. Python Environment ───────────────────────────────────────────────────
echo -e "${YELLOW}[1/6] Python Environment${NC}"

if [ -d ".venv" ]; then
    check "Virtual environment exists" 0
else
    check "Virtual environment exists" 1
    echo "    Create with: python3 -m venv .venv && .venv/bin/pip install -r requirements-prod.txt"
fi

if [ -f ".env" ]; then
    check ".env file exists" 0
else
    check ".env file exists" 1
    echo "    Copy from .env.example: cp .env.example .env"
fi

echo ""

# ─── 2. Django System Check ──────────────────────────────────────────────────
echo -e "${YELLOW}[2/6] Django System Check${NC}"

if .venv/bin/python manage.py check --quiet 2>/dev/null; then
    check "Django system check passes" 0
else
    check "Django system check passes" 1
fi

echo ""

# ─── 3. Database Connection ──────────────────────────────────────────────────
echo -e "${YELLOW}[3/6] Database Connection (Supabase)${NC}"

if grep -q "USE_SQLITE=False" .env 2>/dev/null; then
    DB_HOST=$(grep "^DB_HOST=" .env | cut -d'=' -f2)
    DB_PASSWORD=$(grep "^DB_PASSWORD=" .env | cut -d'=' -f2)

    if [ -n "$DB_HOST" ] && [ "$DB_PASSWORD" != "changeme" ] && [ "$DB_PASSWORD" != "" ]; then
        if .venv/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ksms.settings')
os.environ.setdefault('USE_SQLITE', 'False')
django.setup()
from django.db import connection
connection.ensure_connection()
" 2>/dev/null; then
            check "Supabase connection successful" 0
        else
            check "Supabase connection successful" 1
            echo "    Check DB_HOST, DB_USER, DB_PASSWORD in .env"
        fi
    else
        check "Supabase connection successful" 1
        echo "    Fill in real DB credentials in .env (not changeme)"
    fi
else
    check "Supabase connection skipped (USE_SQLITE=True)" 0
    echo "    Set USE_SQLITE=False when ready for production DB"
fi

echo ""

# ─── 4. Redis Connection (Upstash) ───────────────────────────────────────────
echo -e "${YELLOW}[4/6] Redis Connection (Upstash)${NC}"

REDIS_URL=$(grep "^CELERY_BROKER_URL=" .env 2>/dev/null | cut -d'=' -f2)

if [ -n "$REDIS_URL" ] && [ "$REDIS_URL" != "redis://127.0.0.1:6379/0" ]; then
    if .venv/bin/python -c "
import redis
r = redis.from_url('$REDIS_URL')
r.ping()
print('PONG')
" 2>/dev/null | grep -q "PONG"; then
        check "Upstash Redis connection successful" 0
    else
        check "Upstash Redis connection successful" 1
        echo "    Check CELERY_BROKER_URL in .env"
    fi
else
    check "Upstash Redis not configured yet" 0
    echo "    Set CELERY_BROKER_URL to your Upstash Redis URL"
fi

echo ""

# ─── 5. Email Configuration (Resend) ─────────────────────────────────────────
echo -e "${YELLOW}[5/6] Email Configuration (Resend)${NC}"

EMAIL_HOST=$(grep "^EMAIL_HOST=" .env 2>/dev/null | cut -d'=' -f2)
EMAIL_PASSWORD=$(grep "^EMAIL_HOST_PASSWORD=" .env 2>/dev/null | cut -d'=' -f2)

if [ "$EMAIL_HOST" = "smtp.resend.com" ] && [ -n "$EMAIL_PASSWORD" ] && [ "$EMAIL_PASSWORD" != "changeme" ]; then
    if .venv/bin/python -c "
import smtplib
try:
    server = smtplib.SMTP('smtp.resend.com', 587)
    server.starttls()
    server.login('resend', '$EMAIL_PASSWORD')
    server.quit()
    print('OK')
except Exception as e:
    print(f'FAIL: {e}')
" 2>/dev/null | grep -q "OK"; then
        check "Resend SMTP connection successful" 0
    else
        check "Resend SMTP connection successful" 1
        echo "    Check EMAIL_HOST_PASSWORD (Resend API key) in .env"
    fi
else
    check "Resend not configured yet" 0
    echo "    Set EMAIL_HOST=smtp.resend.com and EMAIL_HOST_PASSWORD=<api-key>"
fi

echo ""

# ─── 6. Security Settings ────────────────────────────────────────────────────
echo -e "${YELLOW}[6/6] Security Settings${NC}"

SECRET_KEY=$(grep "^SECRET_KEY=" .env 2>/dev/null | cut -d'=' -f2)
FIELD_KEY=$(grep "^FIELD_ENCRYPTION_KEY=" .env 2>/dev/null | cut -d'=' -f2)

if [ -n "$SECRET_KEY" ] && [ "$SECRET_KEY" != "your-secret-key-here" ] && [ "$SECRET_KEY" != "imes1_ky@amt_fmt1_@qo9cz\$%re1&nt8i-1onuqlvj48w!1mk" ]; then
    check "SECRET_KEY is set (not default)" 0
else
    check "SECRET_KEY is set (not default)" 1
    echo "    Generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
fi

if [ -n "$FIELD_KEY" ] && [ "$FIELD_KEY" != "your-base64-urlsafe-fernet-key" ]; then
    check "FIELD_ENCRYPTION_KEY is set" 0
else
    check "FIELD_ENCRYPTION_KEY is set" 1
    echo "    Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
fi

DEBUG_VAL=$(grep "^DEBUG=" .env 2>/dev/null | cut -d'=' -f2)
if [ "$DEBUG_VAL" = "False" ]; then
    check "DEBUG=False (production mode)" 0
else
    check "DEBUG=False (production mode)" 1
    echo "    Set DEBUG=False for production"
fi

echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────
echo "=========================================="
echo " Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "=========================================="

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}All checks passed! Ready for Day 2.${NC}"
    exit 0
else
    echo -e "${YELLOW}Fix the failed checks before proceeding.${NC}"
    exit 1
fi
