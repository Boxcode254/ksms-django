from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import School, TimeStampedModel, User
from core.validators import document_upload_validators, image_upload_validators, max_image_size_2mb, percentage_max_validator, percentage_min_validator


class AcademicYear(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="academic_years")
	name = models.CharField(max_length=20)
	start_date = models.DateField()
	end_date = models.DateField()
	is_current = models.BooleanField(default=False, db_index=True)
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ("school_id", "-start_date", "name")
		constraints = [
			models.CheckConstraint(
				condition=Q(end_date__gte=F("start_date")),
				name="academics_year_end_after_start",
			),
			models.UniqueConstraint(
				fields=("school", "name"),
				name="academics_unique_year_name_per_school",
			),
			models.UniqueConstraint(
				fields=("school",),
				condition=Q(is_current=True),
				name="academics_single_current_year_per_school",
			),
		]
		indexes = [
			models.Index(fields=("school", "is_current")),
			models.Index(fields=("school", "-start_date")),
		]
		verbose_name = "Academic year"
		verbose_name_plural = "Academic years"

	def clean(self):
		if self.start_date and self.end_date and self.end_date < self.start_date:
			raise ValidationError({"end_date": "Academic year end date must be on or after the start date."})

	def __str__(self):
		return f"{self.school.code} {self.name}"


class Term(TimeStampedModel):
	class Name(models.TextChoices):
		TERM_1 = "term_1", "Term 1"
		TERM_2 = "term_2", "Term 2"
		TERM_3 = "term_3", "Term 3"

	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="terms")
	academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="terms")
	name = models.CharField(max_length=20, choices=Name.choices)
	start_date = models.DateField()
	end_date = models.DateField()
	is_current = models.BooleanField(default=False, db_index=True)
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ("school_id", "academic_year_id", "start_date")
		constraints = [
			models.CheckConstraint(
				condition=Q(end_date__gte=F("start_date")),
				name="academics_term_end_after_start",
			),
			models.UniqueConstraint(
				fields=("academic_year", "name"),
				name="academics_unique_term_name_per_year",
			),
			models.UniqueConstraint(
				fields=("school",),
				condition=Q(is_current=True),
				name="academics_single_current_term_per_school",
			),
		]
		indexes = [
			models.Index(fields=("school", "is_current")),
			models.Index(fields=("academic_year", "start_date")),
		]
		verbose_name = "Term"
		verbose_name_plural = "Terms"

	def clean(self):
		errors = {}
		if self.academic_year_id and self.school_id and self.academic_year.school_id != self.school_id:
			errors["academic_year"] = "Term school must match the selected academic year."
		if self.start_date and self.end_date and self.end_date < self.start_date:
			errors["end_date"] = "Term end date must be on or after the start date."
		if self.academic_year_id and self.start_date and self.start_date < self.academic_year.start_date:
			errors["start_date"] = "Term start date cannot be before the academic year start date."
		if self.academic_year_id and self.end_date and self.end_date > self.academic_year.end_date:
			errors["end_date"] = "Term end date cannot be after the academic year end date."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.get_name_display()} - {self.academic_year.name}"


class Teacher(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="teachers")
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="teacher_profile",
		limit_choices_to={"role__in": [User.Role.TEACHER, User.Role.SCHOOL_ADMIN]},
	)
	profile_photo = models.ImageField(
		upload_to="teachers/photos/",
		blank=True,
		null=True,
		validators=image_upload_validators + [max_image_size_2mb],
	)
	employee_number = models.CharField(max_length=30)
	tsc_number = models.CharField(max_length=30, blank=True, null=True)
	hire_date = models.DateField(default=timezone.localdate)
	specialization = models.CharField(max_length=255, blank=True)
	assigned_classes = models.ManyToManyField(
		"ClassSection",
		blank=True,
		related_name="assigned_teachers",
	)
	assigned_subjects = models.ManyToManyField(
		"Subject",
		blank=True,
		related_name="assigned_teachers",
	)
	classes_in_charge = models.ManyToManyField(
		"ClassSection",
		blank=True,
		related_name="class_teachers",
	)
	qualification_document = models.FileField(
		upload_to="teachers/qualifications/",
		blank=True,
		null=True,
		validators=document_upload_validators,
	)
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ("school_id", "employee_number", "user_id")
		constraints = [
			models.UniqueConstraint(
				fields=("school", "employee_number"),
				name="academics_unique_teacher_employee_number_per_school",
			),
			models.UniqueConstraint(
				fields=("school", "tsc_number"),
				condition=Q(tsc_number__isnull=False),
				name="academics_unique_teacher_tsc_number_per_school",
			),
		]
		indexes = [
			models.Index(fields=("school", "hire_date")),
			models.Index(fields=("school", "user")),
		]
		verbose_name = "Teacher"
		verbose_name_plural = "Teachers"

	def clean(self):
		errors = {}
		if self.user_id and self.user.role not in {User.Role.TEACHER, User.Role.SCHOOL_ADMIN}:
			errors["user"] = "Selected user must have the Teacher or School Admin role."
		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		from django.db import transaction
		with transaction.atomic():
			super().save(*args, **kwargs)
			if self.user_id and self.user.school_id != self.school_id:
				User.objects.filter(pk=self.user_id).update(school_id=self.school_id)
				self.user.school_id = self.school_id

	def get_assigned_classes(self):
		return ClassSection.objects.filter(
			Q(assigned_teachers=self)
			| Q(class_teachers=self)
			| Q(homeroom_teacher=self)
			| Q(teaching_assignments__teacher=self),
			school_id=self.school_id,
		).distinct().order_by("academic_year_id", "grade_level", "stream")

	def get_classes_in_charge(self):
		return ClassSection.objects.filter(
			Q(class_teachers=self) | Q(homeroom_teacher=self),
			school_id=self.school_id,
		).distinct().order_by(
			"academic_year_id",
			"grade_level",
			"stream",
		)

	def is_assigned_to_class(self, class_section):
		if not class_section or class_section.school_id != self.school_id:
			return False
		return self.get_assigned_classes().filter(pk=class_section.pk).exists()

	def is_class_teacher_for(self, class_section):
		if not class_section or class_section.school_id != self.school_id:
			return False
		return self.get_classes_in_charge().filter(pk=class_section.pk).exists()

	def is_assigned_subject(self, subject):
		if not subject or subject.school_id != self.school_id:
			return False
		return self.assigned_subjects.filter(pk=subject.pk, school_id=self.school_id).exists() or self.teaching_assignments.filter(
			subject_id=subject.pk,
			school_id=self.school_id,
		).exists()

	def can_mark_class_register(self, class_section):
		return self.is_class_teacher_for(class_section)

	def can_access_class_section(self, class_section):
		return self.is_assigned_to_class(class_section)

	def can_teach_subject_in_class(self, *, class_section, subject):
		return self.is_assigned_to_class(class_section) and self.is_assigned_subject(subject)

	def __str__(self):
		return f"{self.user.get_full_name() or self.user.username} ({self.employee_number})"


class ClassSection(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="class_sections")
	academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="class_sections")
	grade_level = models.CharField(max_length=30)
	stream = models.CharField(max_length=20)
	capacity = models.PositiveSmallIntegerField(
		default=40,
		validators=[MinValueValidator(1), MaxValueValidator(200)],
	)
	room_name = models.CharField(max_length=50, blank=True)
	homeroom_teacher = models.ForeignKey(
		Teacher,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="homeroom_sections",
	)
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ("school_id", "academic_year_id", "grade_level", "stream")
		constraints = [
			models.UniqueConstraint(
				fields=("school", "academic_year", "grade_level", "stream"),
				name="academics_unique_section_per_year",
			),
		]
		indexes = [
			models.Index(fields=("school", "academic_year")),
			models.Index(fields=("school", "grade_level", "stream")),
			models.Index(fields=("homeroom_teacher", "academic_year")),
		]
		verbose_name = "Class section"
		verbose_name_plural = "Class sections"

	@property
	def display_name(self):
		if len(self.stream) <= 2:
			return f"{self.grade_level}{self.stream}"
		return f"{self.grade_level} {self.stream}"

	def clean(self):
		errors = {}
		if self.academic_year_id and self.school_id and self.academic_year.school_id != self.school_id:
			errors["academic_year"] = "Class section school must match the selected academic year."
		if self.homeroom_teacher_id and self.school_id and self.homeroom_teacher.school_id != self.school_id:
			errors["homeroom_teacher"] = "Homeroom teacher must belong to the same school."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.display_name} - {self.academic_year.name}"


class Subject(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="subjects")
	name = models.CharField(max_length=100)
	code = models.CharField(max_length=20)
	description = models.TextField(blank=True)
	is_optional = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True, db_index=True)

	class Meta:
		ordering = ("school_id", "name")
		constraints = [
			models.UniqueConstraint(
				fields=("school", "name"),
				name="academics_unique_subject_name_per_school",
			),
			models.UniqueConstraint(
				fields=("school", "code"),
				name="academics_unique_subject_code_per_school",
			),
		]
		indexes = [
			models.Index(fields=("school", "is_active", "name")),
			models.Index(fields=("school", "code")),
		]
		verbose_name = "Subject"
		verbose_name_plural = "Subjects"

	def __str__(self):
		return f"{self.name} ({self.code})"


class TeachingAssignment(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="teaching_assignments")
	class_section = models.ForeignKey(ClassSection, on_delete=models.CASCADE, related_name="teaching_assignments")
	subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="teaching_assignments")
	teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name="teaching_assignments")
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ("school_id", "class_section_id", "subject_id")
		constraints = [
			models.UniqueConstraint(
				fields=("class_section", "subject"),
				name="academics_unique_subject_assignment_per_section",
			),
		]
		indexes = [
			models.Index(fields=("school", "teacher")),
			models.Index(fields=("class_section", "subject")),
		]
		verbose_name = "Teaching assignment"
		verbose_name_plural = "Teaching assignments"

	def clean(self):
		errors = {}
		if self.class_section_id and self.school_id and self.class_section.school_id != self.school_id:
			errors["class_section"] = "Class section must belong to the same school."
		if self.subject_id and self.school_id and self.subject.school_id != self.school_id:
			errors["subject"] = "Subject must belong to the same school."
		if self.teacher_id and self.school_id and self.teacher.school_id != self.school_id:
			errors["teacher"] = "Teacher must belong to the same school."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.class_section.display_name} - {self.subject.name} ({self.teacher.user.get_full_name() or self.teacher.user.username})"


class TimetableEntry(TimeStampedModel):
	class Weekday(models.IntegerChoices):
		MONDAY = 1, "Monday"
		TUESDAY = 2, "Tuesday"
		WEDNESDAY = 3, "Wednesday"
		THURSDAY = 4, "Thursday"
		FRIDAY = 5, "Friday"
		SATURDAY = 6, "Saturday"

	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="timetable_entries")
	term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="timetable_entries")
	teaching_assignment = models.ForeignKey(
		TeachingAssignment,
		on_delete=models.CASCADE,
		related_name="timetable_entries",
	)
	weekday = models.PositiveSmallIntegerField(choices=Weekday.choices, db_index=True)
	start_time = models.TimeField()
	end_time = models.TimeField()
	room_name = models.CharField(max_length=50, blank=True)
	period_label = models.CharField(max_length=30, blank=True)
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ("school_id", "term_id", "weekday", "start_time", "teaching_assignment_id")
		constraints = [
			models.CheckConstraint(
				condition=Q(end_time__gt=F("start_time")),
				name="academics_timetable_end_after_start",
			),
			models.CheckConstraint(
				condition=Q(weekday__gte=1) & Q(weekday__lte=6),
				name="academics_timetable_weekday_range",
			),
			models.UniqueConstraint(
				fields=("term", "teaching_assignment", "weekday", "start_time"),
				name="academics_unique_timetable_slot_per_assignment",
			),
		]
		indexes = [
			models.Index(fields=("school", "term", "weekday", "start_time")),
			models.Index(fields=("teaching_assignment", "weekday", "start_time")),
		]
		verbose_name = "Timetable entry"
		verbose_name_plural = "Timetable entries"

	@property
	def class_section(self):
		return self.teaching_assignment.class_section

	@property
	def subject(self):
		return self.teaching_assignment.subject

	@property
	def teacher(self):
		return self.teaching_assignment.teacher

	def clean(self):
		errors = {}
		if self.room_name:
			self.room_name = self.room_name.strip()

		if self.term_id and self.school_id and self.term.school_id != self.school_id:
			errors["term"] = "Timetable term must belong to the selected school."
		if self.teaching_assignment_id and self.school_id and self.teaching_assignment.school_id != self.school_id:
			errors["teaching_assignment"] = "Teaching assignment must belong to the selected school."
		if (
			self.term_id
			and self.teaching_assignment_id
			and self.term.academic_year_id != self.teaching_assignment.class_section.academic_year_id
		):
			errors["term"] = "Timetable term must align with the teaching assignment academic year."
		if self.start_time and self.end_time and self.end_time <= self.start_time:
			errors["end_time"] = "End time must be after the start time."

		if (
			self.term_id
			and self.teaching_assignment_id
			and self.weekday
			and self.start_time
			and self.end_time
		):
			overlap_queryset = TimetableEntry.objects.filter(
				term_id=self.term_id,
				weekday=self.weekday,
				start_time__lt=self.end_time,
				end_time__gt=self.start_time,
			).exclude(pk=self.pk)

			if overlap_queryset.filter(
				teaching_assignment__class_section_id=self.teaching_assignment.class_section_id
			).exists():
				errors["start_time"] = "This class section already has an overlapping timetable entry."

			if overlap_queryset.filter(
				teaching_assignment__teacher_id=self.teaching_assignment.teacher_id
			).exists():
				errors["teaching_assignment"] = "This teacher already has an overlapping timetable entry."

			if self.room_name and overlap_queryset.filter(room_name__iexact=self.room_name).exists():
				errors["room_name"] = "This room already has an overlapping timetable entry."

		if errors:
			raise ValidationError(errors)

	def __str__(self):
		period = self.period_label or f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
		return f"{self.get_weekday_display()} {period} - {self.class_section.display_name} {self.subject.code}"


class ExamWeightPolicy(TimeStampedModel):
	school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="exam_weight_policy")
	cat_weight = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		default=20,
		validators=[MinValueValidator(0), MaxValueValidator(100)],
	)
	mid_term_weight = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		default=30,
		validators=[MinValueValidator(0), MaxValueValidator(100)],
	)
	end_term_weight = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		default=50,
		validators=[MinValueValidator(0), MaxValueValidator(100)],
	)
	mock_weight = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(100)],
	)

	class Meta:
		ordering = ("school_id",)
		verbose_name = "Exam weight policy"
		verbose_name_plural = "Exam weight policies"

	def clean(self):
		total = (
			(self.cat_weight or 0)
			+ (self.mid_term_weight or 0)
			+ (self.end_term_weight or 0)
			+ (self.mock_weight or 0)
		)
		if total != 100:
			raise ValidationError(
				{
					"cat_weight": "CAT + Mid-Term + End-Term + Mock weights must total 100.",
				}
			)

	def __str__(self):
		return f"{self.school.code} exam weights"


class KNECGradeBand(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="knec_grade_bands")
	grade = models.CharField(max_length=5)
	points = models.DecimalField(
		max_digits=4,
		decimal_places=2,
		validators=[MinValueValidator(0), MaxValueValidator(12)],
	)
	min_score = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		validators=[percentage_min_validator, percentage_max_validator],
	)
	max_score = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		validators=[percentage_min_validator, percentage_max_validator],
	)
	order = models.PositiveSmallIntegerField(default=0)

	class Meta:
		ordering = ("school_id", "order", "-max_score")
		constraints = [
			models.UniqueConstraint(
				fields=("school", "grade"),
				name="academics_unique_knec_grade_per_school",
			),
		]
		indexes = [
			models.Index(fields=("school", "order")),
			models.Index(fields=("school", "min_score", "max_score")),
		]
		verbose_name = "KNEC grade band"
		verbose_name_plural = "KNEC grade bands"

	def clean(self):
		errors = {}
		if self.min_score is not None and self.max_score is not None and self.max_score < self.min_score:
			errors["max_score"] = "Maximum score must be greater than or equal to minimum score."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.school.code} {self.grade} ({self.min_score}-{self.max_score})"


class GradeResult(TimeStampedModel):
	class ExamType(models.TextChoices):
		CAT = "cat", "CAT"
		MID_TERM = "mid_term", "Mid-Term"
		END_TERM = "end_term", "End-Term"
		MOCK = "mock", "Mock"

	enrollment = models.ForeignKey("students.Enrollment", on_delete=models.CASCADE, related_name="grade_results")
	subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="grade_results")
	exam_type = models.CharField(max_length=20, choices=ExamType.choices, default=ExamType.END_TERM, db_index=True)
	score = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		validators=[percentage_min_validator, percentage_max_validator],
	)
	grade = models.CharField(max_length=5, blank=True)
	remarks = models.TextField(blank=True)
	result_document = models.FileField(
		upload_to="academics/results/",
		blank=True,
		null=True,
		validators=document_upload_validators,
	)
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="recorded_grade_results",
	)
	published_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ("-created_at", "subject_id", "exam_type")
		constraints = [
			models.UniqueConstraint(
				fields=("enrollment", "subject", "exam_type"),
				name="academics_unique_result_per_enrollment_subject_exam",
			),
		]
		indexes = [
			models.Index(fields=("subject", "exam_type", "-created_at")),
			models.Index(fields=("recorded_by", "-created_at")),
			models.Index(fields=("enrollment", "-created_at"), name="acad_graderesult_enr_idx"),
		]
		verbose_name = "Grade result"
		verbose_name_plural = "Grade results"

	def clean(self):
		errors = {}
		if self.enrollment_id and self.subject_id and self.subject.school_id != self.enrollment.school_id:
			errors["subject"] = "Subject must belong to the same school as the enrollment."
		if self.exam_type and self.exam_type not in self.ExamType.values:
			errors["exam_type"] = "Select a valid exam type."
		if self.recorded_by_id and self.recorded_by.role not in {User.Role.SCHOOL_ADMIN, User.Role.TEACHER}:
			errors["recorded_by"] = "Results may only be recorded by an admin or teacher account."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.enrollment.student} - {self.subject.code} [{self.get_exam_type_display()}]: {self.score}"
