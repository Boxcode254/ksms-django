from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied



def role_required(*allowed_roles):
    allowed_roles = set(allowed_roles)

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                raise PermissionDenied("You do not have access to this resource.")
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator



def permission_required_403(*permissions):
    permissions = tuple(permissions)

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.has_perms(permissions):
                raise PermissionDenied("You do not have the required permission.")
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


class RoleRequiredMixin(LoginRequiredMixin, AccessMixin):
    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), self.get_login_url(), self.get_redirect_field_name())
        if request.user.role not in set(self.allowed_roles):
            raise PermissionDenied("You do not have access to this resource.")
        return super().dispatch(request, *args, **kwargs)


class RolePermissionRequiredMixin(RoleRequiredMixin, PermissionRequiredMixin):
    raise_exception = True


def user_can_access_school_object(user, obj, school_attr="school"):
    """Check if *user* belongs to the same school as *obj*.

    This is a school-scoping gate only — it does NOT check role-based
    permissions. Callers must apply additional role checks after this
    gate passes (the three helper functions below do this by delegating
    to ``User.can_*`` methods).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    school = getattr(obj, school_attr, None)
    school_id = getattr(school, "pk", None) if school is not None else getattr(obj, f"{school_attr}_id", None)
    if school_id is None or getattr(user, "school_id", None) != school_id:
        return False

    # Only staff roles (admin, teacher) pass the school gate.
    # Students and parents must use their profile-scoped querysets instead.
    return getattr(user, "role", None) in (
        user.Role.SCHOOL_ADMIN,
        user.Role.TEACHER,
    )


def user_can_mark_class_register(user, class_section):
    if not user_can_access_school_object(user, class_section):
        return False
    return user.can_mark_class_register(class_section)


def user_can_access_class_section(user, class_section):
    if not user_can_access_school_object(user, class_section):
        return False
    return user.can_access_class_section(class_section)


def user_can_teach_subject_in_class(user, *, class_section, subject):
    if not user_can_access_school_object(user, class_section):
        return False
    if not user_can_access_school_object(user, subject):
        return False
    return user.can_teach_subject_in_class(class_section=class_section, subject=subject)
