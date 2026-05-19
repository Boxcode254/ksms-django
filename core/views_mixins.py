"""Shared view mixins used across all KSMS apps.

These mixins were previously duplicated in finance, students, attendance,
and communication views.  Import from here instead of redefining locally.
"""

from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect


def htmx_redirect(redirect_to: str) -> HttpResponse:
    """Return a 204 response that instructs HTMX to redirect."""
    response = HttpResponse(status=204)
    response["HX-Redirect"] = redirect_to
    return response


class HtmxTemplateMixin:
    """Return an HTMX-specific partial template when the request comes via
    HTMX (non-boosted).  Full-page navigations use the standard template.
    """
    htmx_template_name = None

    def get_template_names(self):
        htmx = getattr(self.request, "htmx", None)
        is_boosted = bool(getattr(htmx, "boosted", False))
        if htmx and not is_boosted and self.htmx_template_name:
            return [self.htmx_template_name]
        return [self.template_name]


class SuccessMessageFormMixin:
    """Add a success message on form save and redirect via HTMX when applicable."""
    success_message = ""

    def form_valid(self, form):
        self.object = form.save()
        if self.success_message:
            messages.success(self.request, self.success_message)
        if getattr(self.request, "htmx", False):
            return htmx_redirect(self.get_success_url())
        return HttpResponseRedirect(self.get_success_url())
