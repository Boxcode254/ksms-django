from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MinLengthValidator
from django.db import models
from django.apps import apps

from .validators import image_upload_validators, kenya_phone_validator

ROLE_SUPERUSER = "superuser"
ROLE_SCHOOL_ADMIN = "school_admin"
# Backward compatibility alias for older code paths that still import ROLE_ADMIN.
ROLE_ADMIN = ROLE_SCHOOL_ADMIN
ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_PARENT = "parent"

ROLE_GROUPS = {
    ROLE_SUPERUSER: "Superuser",
    ROLE_SCHOOL_ADMIN: "School Admin",
    ROLE_TEACHER: "Teacher",
    ROLE_STUDENT: "Student",
    ROLE_PARENT: "Parent",
}


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class School(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(
        max_length=20,
        unique=True,
        validators=[MinLengthValidator(2)],
        help_text="Short internal school code for future multi-school operations.",
    )
    slug = models.SlugField(max_length=60, unique=True)
    registration_number = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=16, blank=True, validators=[kenya_phone_validator])
    address = models.TextField(blank=True)
    county = models.CharField(max_length=100, blank=True)
    logo = models.ImageField(
        upload_to="schools/logos/",
        blank=True,
        null=True,
        validators=image_upload_validators,
    )
    stamp_image = models.ImageField(
        upload_to="schools/stamps/",
        blank=True,
        null=True,
        validators=image_upload_validators,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=("is_active", "name")),
            models.Index(fields=("county", "name")),
        ]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name


class UserManager(DjangoUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.PARENT)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        if extra_fields.get("role") == User.Role.SUPERUSER:
            extra_fields["is_staff"] = True
            extra_fields["is_superuser"] = True
            extra_fields["school"] = None
        return super().create_user(username, email=email, password=password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.SUPERUSER)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("school", None)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("school") is not None:
            raise ValueError("Superuser must have school=None.")

        return super().create_superuser(username, email=email, password=password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERUSER = ROLE_SUPERUSER, "Superuser"
        SCHOOL_ADMIN = ROLE_SCHOOL_ADMIN, "School Admin"
        TEACHER = ROLE_TEACHER, "Teacher"
        STUDENT = ROLE_STUDENT, "Student"
        PARENT = ROLE_PARENT, "Parent"

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PARENT,
        db_index=True,
    )
    # Phone encryption deferred to post-MVP.
    phone = models.CharField(max_length=16, blank=True, validators=[kenya_phone_validator])
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        validators=image_upload_validators,
    )

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=("role", "school"), name="core_user_role_school_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email)

        if self.role == "admin":
            self.role = self.Role.SCHOOL_ADMIN

        if self.is_superuser:
            self.role = self.Role.SUPERUSER
            self.school = None

        if self.role == self.Role.SUPERUSER or self.is_superuser:
            self.is_staff = True
        else:
            self.is_staff = False

        super().save(*args, **kwargs)

    def has_role(self, *roles):
        return self.role in roles

    @property
    def is_admin_role(self):
        return self.role == self.Role.SCHOOL_ADMIN

    @property
    def is_superuser_role(self):
        return self.role == self.Role.SUPERUSER

    @property
    def is_school_admin_role(self):
        return self.role == self.Role.SCHOOL_ADMIN

    @property
    def is_teacher_role(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student_role(self):
        return self.role == self.Role.STUDENT

    @property
    def is_parent_role(self):
        return self.role == self.Role.PARENT

    def get_teacher_profile(self):
        try:
            return self.teacher_profile
        except ObjectDoesNotExist:
            return None

    def get_assigned_classes(self):
        class_section_model = apps.get_model("academics", "ClassSection")
        if self.is_superuser:
            return class_section_model.objects.all()
        if not self.school_id:
            return class_section_model.objects.none()
        if self.role == self.Role.SCHOOL_ADMIN:
            return class_section_model.objects.filter(school_id=self.school_id)

        teacher_profile = self.get_teacher_profile()
        if not teacher_profile:
            return class_section_model.objects.none()
        return teacher_profile.get_assigned_classes()

    def get_classes_in_charge(self):
        class_section_model = apps.get_model("academics", "ClassSection")
        if self.is_superuser:
            return class_section_model.objects.all()
        if not self.school_id:
            return class_section_model.objects.none()
        if self.role == self.Role.SCHOOL_ADMIN:
            return class_section_model.objects.filter(school_id=self.school_id)

        teacher_profile = self.get_teacher_profile()
        if not teacher_profile:
            return class_section_model.objects.none()
        return teacher_profile.get_classes_in_charge()

    def can_mark_class_register(self, class_section):
        if not class_section:
            return False
        if self.is_superuser:
            return True
        if self.school_id is None or class_section.school_id != self.school_id:
            return False
        if self.role == self.Role.SCHOOL_ADMIN:
            return True

        teacher_profile = self.get_teacher_profile()
        if not teacher_profile:
            return False
        return teacher_profile.can_mark_class_register(class_section)

    def can_access_class_section(self, class_section):
        if not class_section:
            return False
        if self.is_superuser:
            return True
        if self.school_id is None or class_section.school_id != self.school_id:
            return False
        if self.role == self.Role.SCHOOL_ADMIN:
            return True

        teacher_profile = self.get_teacher_profile()
        if not teacher_profile:
            return False
        return teacher_profile.can_access_class_section(class_section)

    def can_teach_subject_in_class(self, *, class_section, subject):
        if not class_section or not subject:
            return False
        if self.is_superuser:
            return True
        if self.school_id is None:
            return False
        if class_section.school_id != self.school_id or subject.school_id != self.school_id:
            return False
        if self.role == self.Role.SCHOOL_ADMIN:
            return True

        teacher_profile = self.get_teacher_profile()
        if not teacher_profile:
            return False
        return teacher_profile.can_teach_subject_in_class(class_section=class_section, subject=subject)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "User login"
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        RESTORE = "restore", "Restore"
        PASSWORD_CHANGE = "password_change", "Password changed"
        ROLE_CHANGE = "role_change", "Role changed"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    old_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("action", "created_at")),
            models.Index(fields=("created_at",)),
        ]
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"

    def __str__(self):
        target = self.object_repr or "system"
        return f"{self.get_action_display()} by {self.actor or 'anonymous'} on {target}"
