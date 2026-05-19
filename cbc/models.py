from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from cbc.services.grading import level_from_score


class CBCLevel(models.TextChoices):
    BE = "BE", "Below Expectation"
    AE = "AE", "Approaching Expectation"
    ME = "ME", "Meeting Expectation"
    EE = "EE", "Exceeding Expectation"


class CoreCompetency(models.TextChoices):
    """The seven KNEC core competencies for CBC."""
    COMMUNICATION = "communication", "Communication & Collaboration"
    CRITICAL_THINKING = "critical_thinking", "Critical Thinking & Problem Solving"
    CREATIVITY = "creativity", "Imagination & Creativity"
    CITIZENSHIP = "citizenship", "Citizenship"
    DIGITAL_LITERACY = "digital_literacy", "Digital Literacy"
    LEARNING_TO_LEARN = "learning_to_learn", "Learning to Learn"
    SELF_EFFICACY = "self_efficacy", "Self-Efficacy"


class Strand(TimeStampedModel):
    """A CBC curriculum strand attached to a Subject + Grade level.

    Strands group the learning outcomes a teacher assesses. Each strand has
    one or more sub-strands (see :class:`SubStrand`).
    """
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.PROTECT,
        related_name="cbc_strands",
    )
    grade_level = models.CharField(max_length=30, db_index=True)
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=10, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("subject_id", "grade_level", "order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("subject", "grade_level", "name"),
                name="cbc_unique_strand_per_subject_grade",
            ),
        ]
        indexes = [
            models.Index(fields=("subject", "grade_level")),
        ]
        verbose_name = "CBC strand"
        verbose_name_plural = "CBC strands"

    def __str__(self):
        return f"{self.subject.name} · {self.grade_level} · {self.name}"


class SubStrand(TimeStampedModel):
    strand = models.ForeignKey(
        Strand,
        on_delete=models.CASCADE,
        related_name="sub_strands",
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=10, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("strand_id", "order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("strand", "name"),
                name="cbc_unique_substrand_per_strand",
            ),
        ]
        verbose_name = "CBC sub-strand"
        verbose_name_plural = "CBC sub-strands"

    def __str__(self):
        return f"{self.strand.name} → {self.name}"


class CBCReport(TimeStampedModel):
    """A CBC report card: one per (enrollment, term)."""
    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="cbc_reports",
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.PROTECT,
        related_name="cbc_reports",
    )
    class_teacher_remarks = models.TextField(blank=True)
    head_teacher_remarks = models.TextField(blank=True)
    values_remarks = models.TextField(
        blank=True,
        help_text="Values, Pertinent and Contemporary Issues (PCIs) summary.",
    )
    general_remark = models.TextField(blank=True)
    total_school_days = models.PositiveSmallIntegerField(null=True, blank=True)
    days_present = models.PositiveSmallIntegerField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbc_reports_generated",
    )

    class Meta:
        ordering = ("-term__start_date", "enrollment_id")
        constraints = [
            models.UniqueConstraint(
                fields=("enrollment", "term"),
                name="cbc_unique_report_per_enrollment_term",
            ),
        ]
        indexes = [
            models.Index(fields=("term", "enrollment")),
        ]
        verbose_name = "CBC report"
        verbose_name_plural = "CBC reports"

    def clean(self):
        errors = {}
        if self.enrollment_id and self.term_id and self.enrollment.term_id != self.term_id:
            errors["term"] = "Report term must match the enrollment's term."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"CBC Report · {self.enrollment.student} · {self.term}"

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def attendance_percentage(self):
        if not self.total_school_days:
            return None
        return round((self.days_present or 0) / self.total_school_days * 100)

    @property
    def average_score(self):
        from django.db.models import Avg
        result = self.assessments.aggregate(avg=Avg("score"))
        return result["avg"]

    @property
    def overall_level(self):
        avg = self.average_score
        if avg is None:
            return None
        return level_from_score(avg)

    def snapshot_attendance(self):
        """Compute and store ``total_school_days`` / ``days_present`` from
        :class:`attendance.DailyAttendance` rows for this enrollment within
        the term's date range. Idempotent — safe to call multiple times.
        """
        from attendance.models import AttendanceStatus, DailyAttendance

        qs = DailyAttendance.objects.filter(
            enrollment=self.enrollment,
            attendance_date__gte=self.term.start_date,
            attendance_date__lte=self.term.end_date,
        )
        self.total_school_days = qs.count()
        self.days_present = qs.filter(status=AttendanceStatus.PRESENT).count()


class CBCAssessment(TimeStampedModel):
    """A single strand/sub-strand score on a :class:`CBCReport`."""
    report = models.ForeignKey(
        CBCReport,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.PROTECT,
        related_name="cbc_assessments",
    )
    strand = models.ForeignKey(
        Strand,
        on_delete=models.PROTECT,
        related_name="cbc_assessments",
        null=True,
        blank=True,
    )
    sub_strand = models.ForeignKey(
        SubStrand,
        on_delete=models.PROTECT,
        related_name="cbc_assessments",
        null=True,
        blank=True,
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    level = models.CharField(max_length=2, choices=CBCLevel.choices, default=CBCLevel.BE, blank=True)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbc_assessments_recorded",
    )

    class Meta:
        ordering = ("subject_id", "strand_id", "sub_strand_id")
        constraints = [
            models.UniqueConstraint(
                fields=("report", "subject", "strand", "sub_strand"),
                name="cbc_unique_assessment_row",
            ),
        ]
        indexes = [
            models.Index(fields=("report", "subject")),
        ]
        verbose_name = "CBC assessment"
        verbose_name_plural = "CBC assessments"

    def clean(self):
        errors = {}
        if self.strand_id and self.subject_id and self.strand.subject_id != self.subject_id:
            errors["strand"] = "Strand must belong to the selected subject."
        if self.sub_strand_id and self.strand_id and self.sub_strand.strand_id != self.strand_id:
            errors["sub_strand"] = "Sub-strand must belong to the selected strand."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Keep level in sync with score on every write.
        if self.score is not None:
            self.level = level_from_score(self.score)
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.sub_strand.name if self.sub_strand_id else (
            self.strand.name if self.strand_id else self.subject.name
        )
        return f"{self.report} · {label}: {self.score} ({self.level})"


class CBCCoreCompetency(TimeStampedModel):
    report = models.ForeignKey(
        CBCReport,
        on_delete=models.CASCADE,
        related_name="core_competencies",
    )
    competency = models.CharField(max_length=40, choices=CoreCompetency.choices)
    level = models.CharField(max_length=2, choices=CBCLevel.choices)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("report_id", "competency")
        constraints = [
            models.UniqueConstraint(
                fields=("report", "competency"),
                name="cbc_unique_core_competency_per_report",
            ),
        ]
        verbose_name = "CBC core competency"
        verbose_name_plural = "CBC core competencies"

    def __str__(self):
        return f"{self.report} · {self.get_competency_display()}: {self.get_level_display()}"
