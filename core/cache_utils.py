"""Cache key builders and TTL constants for KSMS."""

from django.conf import settings
from django.core.cache import cache


CACHE_TTL_NAVIGATION = 3600
CACHE_TTL_STATS = 300
CACHE_TTL_REFERENCE = 1800
CACHE_TTL_ANNOUNCEMENTS = 300
CACHE_TTL_DASHBOARD = getattr(settings, "CACHE_DASHBOARD_SECONDS", 300)


def make_user_cache_key(prefix, user_id, extra=None):
    parts = [prefix, str(user_id)]
    if extra:
        parts.append(str(extra))
    return ":".join(parts)


def nav_cache_key(user):
    role = getattr(user, "role", None)
    school_id = getattr(user, "school_id", None) or 0
    return make_user_cache_key("nav", user.id, f"{role}:{school_id}")


def dashboard_cache_key(user):
    role = getattr(user, "role", None)
    school_id = getattr(user, "school_id", None) or 0
    return make_user_cache_key("dashboard", user.id, f"{role}:{school_id}")


def announcements_cache_key(user):
    school_id = getattr(user, "school_id", None) or 0
    return make_user_cache_key("announcements", user.id, f"school:{school_id}")


def reference_cache_key(prefix, school_id=None):
    parts = ["ref", prefix]
    if school_id:
        parts.append(str(school_id))
    return ":".join(parts)


def get_cached_reference(key_func, ttl=CACHE_TTL_REFERENCE):
    def wrapper(*args, **kwargs):
        cache_key = key_func(*args, **kwargs)
        result = cache.get(cache_key)
        if result is None:
            result = list(key_func._raw(*args, **kwargs))
            cache.set(cache_key, result, ttl)
        return result
    return wrapper


def get_or_cache_reference(cache_key, query_func, ttl=CACHE_TTL_REFERENCE):
    result = cache.get(cache_key)
    if result is None:
        result = list(query_func())
        cache.set(cache_key, result, ttl)
    return result


def invalidate_reference(prefix, school_id=None):
    key = reference_cache_key(prefix, school_id)
    cache.delete(key)

