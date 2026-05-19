#!/usr/bin/env bash
# =============================================================================
# KSMS Key Generator
# Generates SECRET_KEY and FIELD_ENCRYPTION_KEY for .env
# Usage: bash generate_keys.sh
# =============================================================================

echo "=========================================="
echo " KSMS Key Generator"
echo "=========================================="
echo ""

echo "SECRET_KEY:"
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
echo ""

echo "FIELD_ENCRYPTION_KEY:"
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
echo ""

echo "Copy these values into your .env file."
echo "NEVER commit .env to version control."
