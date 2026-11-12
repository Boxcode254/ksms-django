"""School (tenant) scoped querysets for class-based views — task t_d062a79e.

``SchoolScopedQuerysetMixin`` is the single mechanism that keeps staff
queries inside the requester's school. Every generic view that exposes
school-owned rows to staff (lists, detail, update, delete, CSV/PDF
exports) runs its queryset through this mixin.

Contract
--------
* Every concrete view declares ``school_lookup`` — the ORM path from its
  model to ``School`` (``"school_id"`` for a direct FK,
  ``"enrollment__school_id"`` for Invoice, ``"invoice__enrollment__school_id"``
  for Payment, and so on). A view that declares ``model`` without
  ``school_lookup`` raises ``ImproperlyConfigured`` at class-creation
  time, i.e. at import/startup — never a silent unscoped query.
* Superuser (``school=None`` by mandate, ``core/models.py``): NO filter is
  applied. Deliberate and explicit — superusers are global admins. A
  staff user whose ``school_id`` is None is treated the same way,
  matching the card contract and the shipped finance-view convention.
* Cross-school single-object access returns **404**, not 403:
  ``SingleObjectMixin.get_object()`` resolves the row from the scoped
  queryset, so another school's object simply "does not exist".
  (403 would confirm the object exists.)
* Views with custom queryset building override ``get_unscoped_queryset()``
  (or call ``scope_queryset_to_school()`` on an already-built queryset);
  the scoping itself always stays in one place — ``get_queryset()``.

No models, no migrations: this is a query-layer mechanism only.
"""
from django.core.exceptions import ImproperlyConfigured, PermissionDenied


class SchoolScopedQuerysetMixin:
    """Scope a generic view's queryset to the requesting staff user's school."""

    # The ORM path from the view's model to School, e.g. "school_id".
    # REQUIRED on every concrete view; absence fails at import/startup.
    school_lookup = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        model = getattr(cls, "model", None)
        if model is not None and not getattr(cls, "school_lookup", None):
            raise ImproperlyConfigured(
                f"{cls.__qualname__} uses SchoolScopedQuerysetMixin on model "
                f"'{model.__name__}' but does not declare 'school_lookup' "
                "(the ORM path from the model to School, e.g. 'school_id')."
            )

    def get_unscoped_queryset(self):
        """The view's own base queryset, before school scoping.

        Override this (never ``get_queryset``) when a view needs custom
        select_related/filtering; scoping stays in ``get_queryset()``.
        """
        return super().get_queryset()

    def scope_queryset_to_school(self, queryset):
        """Apply the school filter to *queryset* for the current request."""
        user = self.request.user
        if not getattr(user, "is_authenticated", False):
            raise PermissionDenied("Authentication is required.")
        if user.is_superuser or user.school_id is None:
            # Deliberate, explicit no-filter branch (not a fallthrough):
            # superusers have school=None by mandate (core/models.py) and are
            # global admins. A staff user with school=None is treated the
            # same way, matching the card's contract and the convention the
            # existing finance views already ship (e.g. FeeArrearListView /
            # FeeArrearExportCsvView leave school-less staff unfiltered).
            # Residual risk: a misconfigured non-superuser staff account with
            # school=None sees all schools — owner decision, out of scope here.
            return queryset
        return queryset.filter(**{self.school_lookup: user.school_id})

    def get_queryset(self):
        return self.scope_queryset_to_school(self.get_unscoped_queryset())
