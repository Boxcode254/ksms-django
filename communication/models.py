from django.conf import settings
from django.db import models

from core.models import School, TimeStampedModel


class Announcement(TimeStampedModel):
    class Audience(models.TextChoices):
        ALL = "all", "Everyone"
        STUDENTS = "students", "Students"
        PARENTS = "parents", "Parents"
        TEACHERS = "teachers", "Teachers"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="announcements")
    title = models.CharField(max_length=255)
    body = models.TextField()
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.ALL,
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_announcements",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("school", "is_active")),
            models.Index(fields=("school", "audience", "is_active")),
        ]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"

    def __str__(self):
        return f"{self.title} ({self.get_audience_display()})"
