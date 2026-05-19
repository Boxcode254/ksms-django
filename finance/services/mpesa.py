import base64
import hashlib
import hmac
import time
from datetime import datetime

import requests
from django.conf import settings


class MpesaServiceError(Exception):
    pass


# ─── Callback token helpers ────────────────────────────────────────────────
# Daraja cannot send custom headers, so we attach an HMAC-signed token as a
# query parameter.  The token embeds an expiry timestamp so that logged URLs
# cannot be replayed after they expire.

_CALLBACK_TOKEN_TTL_SECONDS = 300  # 5 minutes


def _callback_signing_key() -> bytes:
    """Derive a signing key from configured secrets.

    Falls back to Django SECRET_KEY so that the system works even when
    MPESA_CALLBACK_TOKEN is not set (dev / sandbox environments).
    """
    secret = getattr(settings, "MPESA_CALLBACK_TOKEN", "") or settings.SECRET_KEY
    return secret.encode("utf-8")


def generate_callback_token() -> str:
    """Return a time-limited HMAC token for the M-Pesa callback URL."""
    expiry = int(time.time()) + _CALLBACK_TOKEN_TTL_SECONDS
    message = f"mpesa-callback:{expiry}"
    signature = hmac.new(
        _callback_signing_key(),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{expiry}:{signature}"


def validate_callback_token(token: str) -> bool:
    """Return True if *token* is a valid, non-expired callback token."""
    if not token:
        return False
    parts = token.split(":", 1)
    if len(parts) != 2:
        return False
    try:
        expiry = int(parts[0])
    except ValueError:
        return False
    if time.time() > expiry:
        return False
    message = f"mpesa-callback:{expiry}"
    expected = hmac.new(
        _callback_signing_key(),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(parts[1], expected)


class MpesaService:
    def __init__(self):
        self.base_url = settings.MPESA_BASE_URL.rstrip("/")
        self.timeout = settings.MPESA_TIMEOUT_SECONDS

    def is_enabled(self):
        return settings.MPESA_STK_ENABLED and bool(settings.MPESA_CONSUMER_KEY and settings.MPESA_CONSUMER_SECRET)

    def _token(self):
        endpoint = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        response = requests.get(
            endpoint,
            auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise MpesaServiceError("Unable to obtain M-Pesa access token.")
        return token

    def _password(self):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode("utf-8")
        return base64.b64encode(raw).decode("utf-8"), timestamp

    def start_stk_push(self, *, phone_number, amount, callback_url, account_reference, transaction_desc):
        if not self.is_enabled():
            raise MpesaServiceError("M-Pesa STK push is disabled.")
        if not settings.MPESA_PASSKEY:
            raise MpesaServiceError("MPESA_PASSKEY is not configured.")

        password, timestamp = self._password()
        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": settings.MPESA_TRANSACTION_TYPE,
            "Amount": int(amount),
            "PartyA": phone_number,
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": phone_number,
            "CallBackURL": callback_url,
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:13],
        }

        token = self._token()
        response = requests.post(
            f"{self.base_url}/mpesa/stkpush/v1/processrequest",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if str(data.get("ResponseCode")) != "0":
            raise MpesaServiceError(data.get("errorMessage") or data.get("ResponseDescription") or "STK push request failed")
        return data
