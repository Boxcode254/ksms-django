from django import forms
from django.db.models import Q

from academics.models import ClassSection, Subject, Term
from core.models import School
from students.models import Enrollment

from .models import AttendanceStatus, DailyAttendance, PeriodAttendance


INPUT_CLASS = (
    "block w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 "
    "text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-500 "
    "focus:ring-2 focus:ring-sky-200"
)
TEXTAREA_CLASS = (
    "block min-h-28 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 "
    "text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-500 "
    "focus:ring-2 focus:ring-sky-200"
)


class StyledFieldsMixin:
    def apply_styles(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = TEXTAREA_CLASS
            else:
                widget.attrs["class"] = INPUT_CLASS

            if isinstance(widget, forms.DateInput):
                widget.attrs.setdefault("type", "date")


def active_enrollment_queryset():
    return Enrollment.objects.select_related(
        "student__user",
        "class_section",
        "term",
        "school",
    ).filter(status=Enrollment.Status.ACTIVE).order_by(
        "class_section__grade_level",
        "class_section__stream",
        "student__admission_number",
    )


class AttendanceScopedModelForm(StyledFieldsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        self.term = kwargs.pop("term", None)
        self.class_section = kwargs.pop("class_section", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        resolved_school = self.school or getattr(getattr(self.instance, "enrollment", None), "school", None)
        resolved_term = self.term or getattr(getattr(self.instance, "enrollment", None), "term", None)
        resolved_class_section = self.class_section or getattr(
            getattr(self.instance, "enrollment", None),
            "class_section",
            None,
        )

        enrollment_queryset = active_enrollment_queryset()
        if resolved_school:
            enrollment_queryset = enrollment_queryset.filter(school=resolved_school)
        if resolved_term:
            enrollment_queryset = enrollment_queryset.filter(term=resolved_term)
        if resolved_class_section:
            enrollment_queryset = enrollment_queryset.filter(class_section=resolved_class_section)

        if self.user and self.user.is_authenticated and not self.user.is_superuser:
            if self.user.school_id:
                enrollment_queryset = enrollment_queryset.filter(school_id=self.user.school_id)
            if self.user.role == self.user.Role.TEACHER:
                enrollment_queryset = enrollment_queryset.filter(
                    class_section_id__in=self.user.get_assigned_classes().values_list("id", flat=True)
                )

        self.fields["enrollment"].queryset = enrollment_queryset
        self.apply_styles()


class DailyAttendanceForm(AttendanceScopedModelForm):
    class Meta:
        model = DailyAttendance
        fields = (
            "enrollment",
            "attendance_date",
            "status",
            "remarks",
        )
        widgets = {
            "attendance_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }


class PeriodAttendanceForm(AttendanceScopedModelForm):
    class Meta:
        model = PeriodAttendance
        fields = (
            "enrollment",
            "subject",
            "attendance_date",
            "period_number",
            "status",
            "remarks",
        )
        widgets = {
            "attendance_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        resolved_school = self.school or getattr(getattr(self.instance, "enrollment", None), "school", None)
        subject_queryset = Subject.objects.order_by("name")
        if resolved_school:
            subject_queryset = subject_queryset.filter(school=resolved_school, is_active=True)
        if self.user and self.user.is_authenticated and not self.user.is_superuser:
            if self.user.school_id:
                subject_queryset = subject_queryset.filter(school_id=self.user.school_id)
            if self.user.role == self.user.Role.TEACHER:
                teacher_profile = self.user.get_teacher_profile()
                if teacher_profile:
                    assigned_subject_ids = teacher_profile.assigned_subjects.values_list("id", flat=True)
                    taught_subject_ids = teacher_profile.teaching_assignments.values_list("subject_id", flat=True)
                    subject_queryset = subject_queryset.filter(
                        Q(pk__in=assigned_subject_ids) | Q(pk__in=taught_subject_ids)
                    )
                else:
                    subject_queryset = subject_queryset.none()
        self.fields["subject"].queryset = subject_queryset


class DailyAttendanceFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())
    term = forms.ModelChoiceField(required=False, queryset=Term.objects.none())
    class_section = forms.ModelChoiceField(required=False, queryset=ClassSection.objects.none())
    attendance_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses"), *AttendanceStatus.choices],
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        schools = School.objects.order_by("name")
        terms = Term.objects.select_related("school", "academic_year").order_by(
            "school__name",
            "academic_year__start_date",
            "start_date",
        )
        class_sections = ClassSection.objects.select_related(
            "school",
            "academic_year",
        ).order_by("school__name", "academic_year__start_date", "grade_level", "stream")

        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            if user_school:
                schools = schools.filter(pk=user_school.pk)
                terms = terms.filter(school=user_school)
                class_sections = class_sections.filter(school=user_school)
            else:
                schools = schools.none()
                terms = terms.none()
                class_sections = class_sections.none()

        self.fields["school"].queryset = schools
        self.fields["term"].queryset = terms
        self.fields["class_section"].queryset = class_sections
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type student, admission number, class, or email",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class PeriodAttendanceFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())
    term = forms.ModelChoiceField(required=False, queryset=Term.objects.none())
    class_section = forms.ModelChoiceField(required=False, queryset=ClassSection.objects.none())
    subject = forms.ModelChoiceField(required=False, queryset=Subject.objects.none())
    attendance_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    period_number = forms.IntegerField(required=False, min_value=1, max_value=12)
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses"), *AttendanceStatus.choices],
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        schools = School.objects.order_by("name")
        terms = Term.objects.select_related("school", "academic_year").order_by(
            "school__name",
            "academic_year__start_date",
            "start_date",
        )
        class_sections = ClassSection.objects.select_related(
            "school",
            "academic_year",
        ).order_by("school__name", "academic_year__start_date", "grade_level", "stream")
        subjects = Subject.objects.select_related("school").order_by(
            "school__name",
            "name",
        )

        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            if user_school:
                schools = schools.filter(pk=user_school.pk)
                terms = terms.filter(school=user_school)
                class_sections = class_sections.filter(school=user_school)
                subjects = subjects.filter(school=user_school)
            else:
                schools = schools.none()
                terms = terms.none()
                class_sections = class_sections.none()
                subjects = subjects.none()

        self.fields["school"].queryset = schools
        self.fields["term"].queryset = terms
        self.fields["class_section"].queryset = class_sections
        self.fields["subject"].queryset = subjects
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type student, admission number, class, subject, or code",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )