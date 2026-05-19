from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel


class AttendanceStatus(models.TextChoices):
	PRESENT = "present", "Present"
	ABSENT = "absent", "Absent"
	LATE = "late", "Late"
	EXCUSED = "excused", "Excused"
	SICK = "sick", "Sick"


class AttendanceBase(TimeStampedModel):
	enrollment = models.ForeignKey("students.Enrollment", on_delete=models.CASCADE)
	attendance_date = models.DateField(db_index=True)
	status = models.CharField(max_length=20, choices=AttendanceStatus.choices, db_index=True)
	remarks = models.TextField(blank=True)
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
	)

	class Meta:
		abstract = True

	@property
	def student(self):
		return self.enrollment.student

	@property
	def class_section(self):
		return self.enrollment.class_section


class DailyAttendance(AttendanceBase):
	enrollment = models.ForeignKey("students.Enrollment", on_delete=models.CASCADE, related_name="daily_attendance")
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="daily_attendance_records",
	)

	class Meta:
		ordering = ("-attendance_date", "enrollment_id")
		constraints = [
			models.UniqueConstraint(
				fields=("enrollment", "attendance_date"),
				name="attendance_unique_daily_attendance_per_enrollment",
			),
		]
		indexes = [
			models.Index(fields=("attendance_date", "status")),
			models.Index(fields=("enrollment", "attendance_date")),
			models.Index(fields=("enrollment", "attendance_date", "status"), name="att_daily_enr_dt_st_idx"),
		]
		verbose_name = "Daily attendance"
		verbose_name_plural = "Daily attendance"

	def __str__(self):
		return f"{self.student} - {self.attendance_date} ({self.get_status_display()})"


class PeriodAttendance(AttendanceBase):
	enrollment = models.ForeignKey("students.Enrollment", on_delete=models.CASCADE, related_name="period_attendance")
	subject = models.ForeignKey(
		"academics.Subject",
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name="period_attendance_records",
	)
	period_number = models.PositiveSmallIntegerField(
		validators=[MinValueValidator(1), MaxValueValidator(12)],
	)
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="period_attendance_records",
	)

	class Meta:
		ordering = ("-attendance_date", "period_number", "enrollment_id")
		constraints = [
			models.UniqueConstraint(
				fields=("enrollment", "attendance_date", "period_number"),
				name="attendance_unique_period_attendance_per_enrollment",
			),
		]
		indexes = [
			models.Index(fields=("attendance_date", "period_number", "status")),
			models.Index(fields=("subject", "attendance_date")),
		]
		verbose_name = "Period attendance"
		verbose_name_plural = "Period attendance"

	def clean(self):
		errors = {}
		if self.subject_id and self.enrollment_id and self.subject.school_id != self.enrollment.school_id:
			errors["subject"] = "Subject must belong to the same school as the enrollment."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.student} - {self.attendance_date} period {self.period_number} ({self.get_status_display()})"
