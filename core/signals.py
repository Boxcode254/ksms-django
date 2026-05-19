from django.contrib.auth.models import Group, Permission
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.db.models.signals import post_delete, post_init, post_migrate, post_save, pre_save
from django.dispatch import receiver

from .models import AuditLog, ROLE_GROUPS, User
from .request_context import get_client_ip, get_current_request, get_user_agent

AUDIT_APP_LABELS = {"core", "students", "academics", "attendance", "finance", "communication"}
TEACHER_PERMISSION_CODES = {
    "view_student",
    "view_guardian",
    "view_studentguardianrelationship",
    "view_enrollment",
    "view_academicyear",
    "view_term",
    "view_classsection",
    "view_subject",
    "view_teachingassignment",
    "view_timetableentry",
    "view_graderesult",
    "add_graderesult",
    "change_graderesult",
    "view_dailyattendance",
    "add_dailyattendance",
    "change_dailyattendance",
    "view_periodattendance",
    "add_periodattendance",
    "change_periodattendance",
    "view_announcement",
    "add_announcement",
    "change_announcement",
    "delete_announcement",
}

PARENT_PERMISSION_CODES = {
    "view_invoice",
    "view_payment",
    "view_announcement",
}

STUDENT_PERMISSION_CODES = {
    "view_enrollment",
    "view_timetableentry",
    "view_graderesult",
    "view_dailyattendance",
    "view_invoice",
    "view_payment",
    "view_announcement",
}

_original_user_state = {}


def get_actor(request):
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user
    return None


def should_audit_sender(sender):
    return (
        hasattr(sender, "_meta")
        and not sender._meta.auto_created
        and sender._meta.app_label in AUDIT_APP_LABELS
        and sender._meta.model_name != "auditlog"
    )


def record_audit_event(*, action, instance=None, actor=None, request=None, metadata=None, old_value=None, new_value=None):
    content_type = None
    object_id = ""
    object_repr = ""

    if instance is not None:
        content_type = ContentType.objects.get_for_model(instance, for_concrete_model=False)
        object_id = str(instance.pk or "")
        object_repr = str(instance)[:255]

    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        content_type=content_type,
        object_id=object_id,
        object_repr=object_repr,
        old_value=old_value or {},
        new_value=new_value or {},
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata=metadata or {},
    )


@receiver(post_init, sender=User)
def cache_user_original_state(sender, instance, **kwargs):
    if instance.pk:
        _original_user_state[instance.pk] = {
            "role": instance.__dict__.get("role"),
            "is_superuser": instance.__dict__.get("is_superuser", False),
            "is_active": instance.__dict__.get("is_active", True),
            "email": instance.__dict__.get("email"),
        }


@receiver(pre_save, sender=User)
def detect_user_role_change(sender, instance, **kwargs):
    if not instance.pk:
        return
    original = _original_user_state.get(instance.pk)
    if not original:
        return
    if original["role"] != instance.role:
        request = get_current_request()
        record_audit_event(
            action=AuditLog.Action.ROLE_CHANGE,
            instance=instance,
            actor=get_actor(request),
            request=request,
            old_value={"role": original["role"]},
            new_value={"role": instance.role},
            metadata={"event": "role_changed"},
        )


@receiver(post_save, sender=User)
def sync_user_role_group(sender, instance, **kwargs):
    sync_role_group_membership(instance)
    if instance.pk:
        _original_user_state[instance.pk] = {
            "role": instance.__dict__.get("role"),
            "is_superuser": instance.__dict__.get("is_superuser", False),
            "is_active": instance.__dict__.get("is_active", True),
            "email": instance.__dict__.get("email"),
        }


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    record_audit_event(
        action=AuditLog.Action.LOGIN,
        instance=user,
        actor=user,
        request=request,
        metadata={"event": "user_logged_in"},
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    record_audit_event(
        action=AuditLog.Action.LOGIN,
        instance=user,
        actor=user,
        request=request,
        metadata={"event": "user_logged_out"},
    )


def log_password_change(user, request=None):
    record_audit_event(
        action=AuditLog.Action.PASSWORD_CHANGE,
        instance=user,
        actor=user,
        request=request,
        metadata={"event": "password_changed"},
    )


@receiver(post_save)
def log_model_save(sender, instance, created, raw, update_fields=None, **kwargs):
    if raw or not should_audit_sender(sender):
        return

    request = get_current_request()
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE

    new_data = {}
    if not created and update_fields:
        for field_name in update_fields:
            value = getattr(instance, field_name, None)
            if isinstance(value, models.Model):
                new_data[field_name] = str(value.pk) if value else None
            else:
                new_data[field_name] = str(value) if value is not None else None

    record_audit_event(
        action=action,
        instance=instance,
        actor=get_actor(request),
        request=request,
        metadata={
            "app_label": sender._meta.app_label,
            "model": sender._meta.model_name,
            "created": created,
        },
        new_value=new_data if new_data else None,
    )


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    if not should_audit_sender(sender):
        return

    request = get_current_request()
    record_audit_event(
        action=AuditLog.Action.DELETE,
        instance=instance,
        actor=get_actor(request),
        request=request,
        metadata={
            "app_label": sender._meta.app_label,
            "model": sender._meta.model_name,
        },
    )


@receiver(post_migrate)
def bootstrap_role_groups(sender, **kwargs):
    required_tables = {
        User._meta.db_table,
        Group._meta.db_table,
        Permission._meta.db_table,
    }
    if not required_tables.issubset(set(connection.introspection.table_names())):
        return

    superuser_group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[User.Role.SUPERUSER])
    school_admin_group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[User.Role.SCHOOL_ADMIN])
    teacher_group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[User.Role.TEACHER])
    student_group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[User.Role.STUDENT])
    parent_group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[User.Role.PARENT])

    superuser_group.permissions.set(Permission.objects.all())
    school_admin_group.permissions.set(Permission.objects.all())
    teacher_group.permissions.set(
        Permission.objects.filter(codename__in=TEACHER_PERMISSION_CODES)
    )
    student_group.permissions.set(
        Permission.objects.filter(codename__in=STUDENT_PERMISSION_CODES)
    )
    parent_group.permissions.set(
        Permission.objects.filter(codename__in=PARENT_PERMISSION_CODES)
    )

    for user in User.objects.all().only("id", "role"):
        sync_role_group_membership(user)


def sync_role_group_membership(user):
    target_group_name = ROLE_GROUPS.get(user.role)
    if not target_group_name or not user.pk:
        return

    for group_name in ROLE_GROUPS.values():
        if group_name == target_group_name:
            continue
        group = Group.objects.filter(name=group_name).first()
        if group:
            user.groups.remove(group)

    target_group, _ = Group.objects.get_or_create(name=target_group_name)
    user.groups.add(target_group)
