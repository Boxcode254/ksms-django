from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.encryption import fingerprint_value
from core.fields import EncryptedTextField
from core.models import School, TimeStampedModel, User
from core.validators import document_upload_validators, image_upload_validators


class SoftDeleteQuerySet(models.QuerySet):
	def delete(self):
		return self.update(deleted_at=timezone.now())


class StudentQuerySet(SoftDeleteQuerySet):
	def active(self):
		return self.filter(deleted_at__isnull=True)

	def deleted(self):
		return self.filter(deleted_at__isnull=False)

	def for_teacher(self, user):
		if not getattr(user, "is_authenticated", False):
			return self.none()
		if getattr(user, "role", None) != User.Role.TEACHER:
			return self.none()
		if not getattr(user, "school_id", None):
			return self.none()

		# Teacher visibility is class-scoped: assigned classes + classes in charge.
		assigned_class_ids = user.get_assigned_classes().values_list("id", flat=True)
		return self.filter(
			school_id=user.school_id,
			enrollments__class_section_id__in=assigned_class_ids,
			enrollments__status="active",
		)

	def for_user_visibility(self, user):
		if not getattr(user, "is_authenticated", False):
			return self.none()
		if getattr(user, "is_superuser", False):
			return self
		if not getattr(user, "school_id", None):
			return self.none()
		if user.role == User.Role.SCHOOL_ADMIN:
			return self.filter(school_id=user.school_id)
		if user.role == User.Role.TEACHER:
			return self.for_teacher(user)
		return self.none()


class StudentManager(models.Manager):
	def get_queryset(self):
		return StudentQuerySet(self.model, using=self._db).active()

	def for_teacher(self, user):
		return self.get_queryset().for_teacher(user)

	def for_user_visibility(self, user):
		return self.get_queryset().for_user_visibility(user)


class AllStudentManager(models.Manager):
	def get_queryset(self):
		return StudentQuerySet(self.model, using=self._db)


class Student(TimeStampedModel):
	class Gender(models.TextChoices):
		MALE = "male", "Male"
		FEMALE = "female", "Female"
		OTHER = "other", "Other"

	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		SUSPENDED = "suspended", "Suspended"
		TRANSFERRED = "transferred", "Transferred"
		GRADUATED = "graduated", "Graduated"
		INACTIVE = "inactive", "Inactive"

	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="students")
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="student_profile",
		limit_choices_to={"role": User.Role.STUDENT},
	)
	admission_number = models.CharField(max_length=30)
	date_of_birth = models.DateField(blank=True, null=True)
	gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
	admission_date = models.DateField(default=timezone.localdate)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
	photo = models.ImageField(
		upload_to="students/photos/",
		blank=True,
		null=True,
		validators=image_upload_validators,
	)
	admission_document = models.FileField(
		upload_to="students/documents/",
		blank=True,
		null=True,
		validators=document_upload_validators,
	)
	address = models.TextField(blank=True)
	notes = models.TextField(blank=True)
	deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

	class Meta:
		ordering = ("school_id", "admission_number")
		constraints = [
			models.UniqueConstraint(
				fields=("school", "admission_number"),
				name="students_unique_admission_number_per_school",
			),
		]
		indexes = [
			models.Index(fields=("school", "status")),
			models.Index(fields=("school", "admission_date")),
		]
		verbose_name = "Student"
		verbose_name_plural = "Students"

	objects = StudentManager()
	all_objects = AllStudentManager()

	@property
	def is_deleted(self):
		return self.deleted_at is not None

	def delete(self, *args, **kwargs):
		from django.db import transaction
		with transaction.atomic():
			self.deleted_at = timezone.now()
			self.save(update_fields=["deleted_at", "updated_at"])
			Enrollment.objects.filter(student=self, deleted_at__isnull=True).update(
				deleted_at=timezone.now()
			)
			from finance.models import Invoice, Payment
			invoices = Invoice.objects.filter(
				enrollment__student=self, deleted_at__isnull=True
			)
			invoices.update(deleted_at=timezone.now())
			Payment.objects.filter(
				invoice__in=invoices, deleted_at__isnull=True
			).update(deleted_at=timezone.now())

	def clean(self):
		if self.user_id and self.user.role != User.Role.STUDENT:
			raise ValidationError({"user": "Selected user must have the Student role."})

	def save(self, *args, **kwargs):
		from django.db import transaction
		with transaction.atomic():
			super().save(*args, **kwargs)
			if self.user_id and self.user.school_id != self.school_id:
				User.objects.filter(pk=self.user_id).update(school_id=self.school_id)
				self.user.school_id = self.school_id

	def __str__(self):
		return f"{self.admission_number} - {self.user.get_full_name() or self.user.username}"


class GuardianQuerySet(SoftDeleteQuerySet):
	def active(self):
		return self.filter(deleted_at__isnull=True)

	def deleted(self):
		return self.filter(deleted_at__isnull=False)


class GuardianManager(models.Manager):
	def get_queryset(self):
		return GuardianQuerySet(self.model, using=self._db).active()


class AllGuardianManager(models.Manager):
	def get_queryset(self):
		return GuardianQuerySet(self.model, using=self._db)


class Guardian(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="guardians")
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="guardian_profile",
		limit_choices_to={"role": User.Role.PARENT},
	)
	occupation = models.CharField(max_length=120, blank=True)
	# National ID encrypted - Kenya DPA compliance
	national_id = EncryptedTextField(blank=True, null=True)
	national_id_fingerprint = models.CharField(max_length=64, blank=True, null=True, editable=False, db_index=True)
	postal_address = models.TextField(blank=True)
	identification_document = models.FileField(
		upload_to="guardians/identification/",
		blank=True,
		null=True,
		validators=document_upload_validators,
	)
	notes = models.TextField(blank=True)
	deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

	class Meta:
		ordering = ("school_id", "user_id")
		constraints = [
			models.UniqueConstraint(
				fields=("school", "national_id_fingerprint"),
				condition=Q(national_id_fingerprint__isnull=False),
				name="students_unique_guardian_national_id_fingerprint_per_school",
			),
		]
		indexes = [
			models.Index(fields=("school", "user")),
		]
		verbose_name = "Guardian"
		verbose_name_plural = "Guardians"

	objects = GuardianManager()
	all_objects = AllGuardianManager()

	@property
	def is_deleted(self):
		return self.deleted_at is not None

	def delete(self, *args, **kwargs):
		from django.db import transaction
		with transaction.atomic():
			self.deleted_at = timezone.now()
			self.save(update_fields=["deleted_at", "updated_at"])
			StudentGuardianRelationship.objects.filter(
				guardian=self, deleted_at__isnull=True
			).update(deleted_at=timezone.now())

	def clean(self):
		if self.user_id and self.user.role != User.Role.PARENT:
			raise ValidationError({"user": "Selected user must have the Parent role."})

	def save(self, *args, **kwargs):
		from django.db import transaction
		self.national_id_fingerprint = fingerprint_value(self.national_id)
		with transaction.atomic():
			super().save(*args, **kwargs)
			if self.user_id and self.user.school_id != self.school_id:
				User.objects.filter(pk=self.user_id).update(school_id=self.school_id)
				self.user.school_id = self.school_id

	def __str__(self):
		return self.user.get_full_name() or self.user.username


class StudentGuardianRelationshipQuerySet(SoftDeleteQuerySet):
	def active(self):
		return self.filter(deleted_at__isnull=True)

	def deleted(self):
		return self.filter(deleted_at__isnull=False)


class StudentGuardianRelationshipManager(models.Manager):
	def get_queryset(self):
		return StudentGuardianRelationshipQuerySet(self.model, using=self._db).active()


class AllStudentGuardianRelationshipManager(models.Manager):
	def get_queryset(self):
		return StudentGuardianRelationshipQuerySet(self.model, using=self._db)


class StudentGuardianRelationship(TimeStampedModel):
	class Relationship(models.TextChoices):
		FATHER = "father", "Father"
		MOTHER = "mother", "Mother"
		GUARDIAN = "guardian", "Guardian"
		SPONSOR = "sponsor", "Sponsor"
		OTHER = "other", "Other"

	student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardian_relationships")
	guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="student_relationships")
	relationship = models.CharField(max_length=20, choices=Relationship.choices)
	is_primary_contact = models.BooleanField(default=False, db_index=True)
	is_emergency_contact = models.BooleanField(default=False, db_index=True)
	is_fee_payer = models.BooleanField(default=False, db_index=True)
	notes = models.TextField(blank=True)
	deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

	class Meta:
		ordering = ("student_id", "-is_primary_contact", "guardian_id")
		constraints = [
			models.UniqueConstraint(
				fields=("student", "guardian"),
				name="students_unique_guardian_per_student",
			),
			models.UniqueConstraint(
				fields=("student",),
				condition=Q(is_primary_contact=True),
				name="students_single_primary_guardian_per_student",
			),
		]
		indexes = [
			models.Index(fields=("guardian", "is_fee_payer")),
			models.Index(fields=("student", "is_primary_contact")),
		]
		verbose_name = "Student guardian relationship"
		verbose_name_plural = "Student guardian relationships"

	objects = StudentGuardianRelationshipManager()
	all_objects = AllStudentGuardianRelationshipManager()

	@property
	def is_deleted(self):
		return self.deleted_at is not None

	def delete(self, *args, **kwargs):
		self.deleted_at = timezone.now()
		self.save(update_fields=["deleted_at", "updated_at"])

	def clean(self):
		errors = {}
		if self.student_id and self.guardian_id and self.student.school_id != self.guardian.school_id:
			errors["guardian"] = "Guardian must belong to the same school as the student."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.student} - {self.guardian} ({self.get_relationship_display()})"


class EnrollmentQuerySet(SoftDeleteQuerySet):
	def active(self):
		return self.filter(deleted_at__isnull=True)

	def deleted(self):
		return self.filter(deleted_at__isnull=False)


class EnrollmentManager(models.Manager):
	def get_queryset(self):
		return EnrollmentQuerySet(self.model, using=self._db).active()


class AllEnrollmentManager(models.Manager):
	def get_queryset(self):
		return EnrollmentQuerySet(self.model, using=self._db)


class Enrollment(TimeStampedModel):
	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		COMPLETED = "completed", "Completed"
		TRANSFERRED = "transferred", "Transferred"
		WITHDRAWN = "withdrawn", "Withdrawn"

	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="enrollments")
	student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
	academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="enrollments")
	term = models.ForeignKey("academics.Term", on_delete=models.PROTECT, related_name="enrollments")
	class_section = models.ForeignKey("academics.ClassSection", on_delete=models.PROTECT, related_name="enrollments")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
	start_date = models.DateField(default=timezone.localdate)
	end_date = models.DateField(blank=True, null=True)
	roll_number = models.PositiveIntegerField(blank=True, null=True)
	notes = models.TextField(blank=True)
	deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

	class Meta:
		ordering = ("school_id", "-start_date", "student_id")
		constraints = [
			models.CheckConstraint(
				condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
				name="students_enrollment_end_after_start",
			),
			models.UniqueConstraint(
				fields=("student", "term"),
				condition=Q(status="active"),
				name="students_single_active_enrollment_per_term",
			),
			models.UniqueConstraint(
				fields=("class_section", "roll_number"),
				condition=Q(roll_number__isnull=False),
				name="students_unique_roll_number_per_section",
			),
		]
		indexes = [
			models.Index(fields=("school", "term", "status")),
			models.Index(fields=("student", "term")),
			models.Index(fields=("class_section", "status")),
		]
		verbose_name = "Enrollment"
		verbose_name_plural = "Enrollments"

	objects = EnrollmentManager()
	all_objects = AllEnrollmentManager()

	@property
	def is_deleted(self):
		return self.deleted_at is not None

	def delete(self, *args, **kwargs):
		self.deleted_at = timezone.now()
		self.save(update_fields=["deleted_at", "updated_at"])

	def clean(self):
		errors = {}
		if self.student_id and self.school_id and self.student.school_id != self.school_id:
			errors["student"] = "Student must belong to the selected school."
		if self.academic_year_id and self.school_id and self.academic_year.school_id != self.school_id:
			errors["academic_year"] = "Academic year must belong to the selected school."
		if self.term_id and self.school_id and self.term.school_id != self.school_id:
			errors["term"] = "Term must belong to the selected school."
		if self.class_section_id and self.school_id and self.class_section.school_id != self.school_id:
			errors["class_section"] = "Class section must belong to the selected school."
		if self.term_id and self.academic_year_id and self.term.academic_year_id != self.academic_year_id:
			errors["term"] = "Term must belong to the selected academic year."
		if self.class_section_id and self.academic_year_id and self.class_section.academic_year_id != self.academic_year_id:
			errors["class_section"] = "Class section must belong to the selected academic year."
		if self.end_date and self.start_date and self.end_date < self.start_date:
			errors["end_date"] = "Enrollment end date must be on or after the start date."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.student} - {self.class_section.display_name} ({self.term.get_name_display()})"
