"""Custom allauth adapter integrating rate limiting for auth endpoints."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse

from .ratelimit import (
    check_login_rate_limit,
    check_password_reset_rate_limit,
    check_signup_rate_limit,
    rate_limit_response,
)
from .signals import log_password_change


class RateLimitedAccountAdapter(DefaultAccountAdapter):
    def pre_login(self, request, user, **kwargs):
        ip = request.META.get("REMOTE_ADDR", "")
        response = check_login_rate_limit(ip)
        if response:
            raise ImmediateHttpResponse(response=response)
        super().pre_login(request, user, **kwargs)

    def is_open_for_signup(self, request):
        if request:
            ip = request.META.get("REMOTE_ADDR", "")
            response = check_signup_rate_limit(ip)
            if response:
                raise ImmediateHttpResponse(response=response)
        return super().is_open_for_signup(request)

    def send_mail(self, template_prefix, email, context):
        request = context.get("request") if isinstance(context, dict) else None
        if request:
            ip = request.META.get("REMOTE_ADDR", "")
            response = check_password_reset_rate_limit(ip)
            if response:
                raise ImmediateHttpResponse(response=response)
        super().send_mail(template_prefix, email, context)

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit)
        log_password_change(user, request)
        return user
