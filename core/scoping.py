from django.core.exceptions import PermissionDenied
from django.db import models


class SchoolScopedQuerySet(models.QuerySet):
    def for_user(self, user, school_lookup="school"):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        if getattr(user, "is_superuser", False):
            return self
        school = getattr(user, "school", None)
        if school is None:
            return self.none()
        return self.filter(**{school_lookup: school})


class SchoolScopedManager(models.Manager):
    def get_queryset(self):
        return SchoolScopedQuerySet(self.model, using=self._db)

    def for_user(self, user, school_lookup="school"):
        return self.get_queryset().for_user(user, school_lookup=school_lookup)


class SchoolScopeMixin:
    school_filter_lookup = "school"
    allow_without_school_for_roles = ()

    def scope_queryset_to_user_school(self, queryset):
        user = self.request.user
        if not user.is_authenticated:
            raise PermissionDenied("Authentication is required.")
        if user.is_superuser:
            return queryset
        if user.role in set(self.allow_without_school_for_roles):
            return queryset
        if user.school_id is None:
            raise PermissionDenied("User is not linked to a school.")
        return queryset.filter(**{self.school_filter_lookup: user.school})
