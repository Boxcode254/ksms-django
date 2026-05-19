from django.conf import settings
from django.utils.cache import patch_cache_control

from .ratelimit import get_rate_limit_info
from .request_context import clear_current_request, set_current_request


class RateLimitHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        ip = request.META.get("REMOTE_ADDR", "")
        info = get_rate_limit_info(f"login:{ip}", 10, 3600)
        response.setdefault("X-RateLimit-Limit", str(info["limit"]))
        response.setdefault("X-RateLimit-Remaining", str(info["remaining"]))
        response.setdefault("X-RateLimit-Reset", str(info["reset"]))
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not settings.DEBUG:
            csp_parts = [
                "default-src " + getattr(settings, "CSP_DEFAULT_SRC", "'self'"),
                "script-src " + getattr(settings, "CSP_SCRIPT_SRC", "'self'"),
                "style-src " + getattr(settings, "CSP_STYLE_SRC", "'self'"),
                "img-src " + getattr(settings, "CSP_IMG_SRC", "'self' data: https:"),
                "connect-src " + getattr(settings, "CSP_CONNECT_SRC", "'self'"),
                "font-src " + getattr(settings, "CSP_FONT_SRC", "'self'"),
                "frame-ancestors " + getattr(settings, "CSP_FRAME_ANCESTORS", "'none'"),
            ]
            response.setdefault("Content-Security-Policy", "; ".join(csp_parts))
            response.setdefault(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=(), payment=()",
            )

        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        return response


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            response = self.get_response(request)
        finally:
            clear_current_request()

        if getattr(request, "user", None) and request.user.is_authenticated:
            patch_cache_control(
                response,
                private=True,
                no_cache=True,
                no_store=True,
                must_revalidate=True,
                max_age=0,
            )
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response
