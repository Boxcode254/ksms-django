"""Lightweight rate limiter using Django's cache framework.

Provides a simple sliding-window counter that works with any cache backend
(locmem, Redis, Memcached).  No external dependencies required.
"""

import time

from django.core.cache import cache
from django.http import JsonResponse


def is_rate_limited(key: str, limit: int, window: int) -> bool:
    """Return True if *key* has exceeded *limit* requests in *window* seconds.

    Uses a sliding-window counter stored in the cache.  The counter key
    expires automatically after the window passes.

    Args:
        key: Unique identifier for the rate-limit bucket (e.g. IP address).
        limit: Maximum number of requests allowed within the window.
        window: Time window in seconds.

    Returns:
        True if the request should be rejected (rate-limited).
    """
    cache_key = f"ratelimit:{key}"
    current = cache.get(cache_key, 0)
    if current is None:
        current = 0
    if current >= limit:
        return True
    cache.set(cache_key, current + 1, timeout=window)
    return False


def get_rate_limit_info(key: str, limit: int, window: int) -> dict:
    """Return rate limit info for a key without incrementing the counter.

    Returns:
        dict with 'limit', 'remaining', 'reset' keys.
    """
    cache_key = f"ratelimit:{key}"
    current = cache.get(cache_key, 0)
    if current is None:
        current = 0
    # cache.ttl() is only available on django-redis; fall back to window
    # for LocMemCache and other backends that don't expose TTL.
    ttl = getattr(cache, "ttl", lambda k: None)(cache_key)
    if ttl is None or ttl <= 0:
        ttl = window
    return {
        "limit": limit,
        "remaining": max(0, limit - current),
        "reset": int(time.time()) + ttl,
    }


def rate_limit_response(retry_after: int, message: str = "Too many requests. Please try again later.") -> JsonResponse:
    """Return a standard 429 Too Many Requests JSON response."""
    response = JsonResponse({"ok": False, "error": message}, status=429)
    response["Retry-After"] = str(retry_after)
    return response


def check_rate_limit(key: str, limit: int, window: int) -> JsonResponse | None:
    """Convenience helper: return a 429 response if rate-limited, else None.

    Usage in a view::

        response = check_rate_limit(request.META.get("REMOTE_ADDR", ""), limit=5, window=60)
        if response:
            return response
    """
    if is_rate_limited(key, limit, window):
        return rate_limit_response(window)
    return None


RATE_LIMIT_LOGIN = 10
RATE_LIMIT_LOGIN_WINDOW = 3600

RATE_LIMIT_PASSWORD_RESET = 3
RATE_LIMIT_PASSWORD_RESET_WINDOW = 3600

RATE_LIMIT_SIGNUP = 5
RATE_LIMIT_SIGNUP_WINDOW = 3600


def check_login_rate_limit(ip: str) -> JsonResponse | None:
    return check_rate_limit(f"login:{ip}", RATE_LIMIT_LOGIN, RATE_LIMIT_LOGIN_WINDOW)


def check_password_reset_rate_limit(ip: str) -> JsonResponse | None:
    return check_rate_limit(
        f"password_reset:{ip}",
        RATE_LIMIT_PASSWORD_RESET,
        RATE_LIMIT_PASSWORD_RESET_WINDOW,
    )


def check_signup_rate_limit(ip: str) -> JsonResponse | None:
    return check_rate_limit(f"signup:{ip}", RATE_LIMIT_SIGNUP, RATE_LIMIT_SIGNUP_WINDOW)
