import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _normalize_identifier(value):
    if value in (None, ""):
        return ""
    text = str(value).strip().upper()
    return "".join(ch for ch in text if ch.isalnum())


def _derive_dev_key(secret):
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


@lru_cache(maxsize=1)
def get_fernet():
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    key = key.strip() if isinstance(key, str) else ""

    if not key:
        if settings.DEBUG or getattr(settings, "RUNNING_TESTS", False):
            key = _derive_dev_key(settings.SECRET_KEY)
        else:
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must be configured for encrypted fields.")

    return Fernet(key.encode("utf-8"))


def encrypt_value(value):
    if value in (None, ""):
        return value
    token = get_fernet().encrypt(str(value).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(value, strict=False):
    if value in (None, ""):
        return value

    try:
        raw = get_fernet().decrypt(str(value).encode("utf-8"))
    except InvalidToken:
        if strict:
            raise
        return value

    return raw.decode("utf-8")


def fingerprint_value(value):
    normalized = _normalize_identifier(value)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def mask_identifier(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "X" * len(text)
    return f"{text[:-4]}XXXX"
