from django import forms
from django.db.models import Q

from core.models import School, User
from students.forms import UserBackedProfileFormMixin
from students.models import Enrollment

from .models import AcademicYear, ClassSection, GradeResult, Subject, Teacher, TeachingAssignment, Term, TimetableEntry


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

BOOLEAN_FILTER_CHOICES = (
    ("", "All"),
    ("true", "Yes"),
    ("false", "No"),
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
            if isinstance(widget, forms.TimeInput):
                widget.attrs.setdefault("type", "time")


def section_queryset():
    return ClassSection.objects.select_related(
        "school",
        "academic_year",
        "homeroom_teacher__user",
    ).order_by("school__name", "academic_year__start_date", "grade_level", "stream")


def subject_queryset():
    return Subject.objects.select_related("school").order_by("school__name", "name")


def teacher_queryset():
    return Teacher.objects.select_related("school", "user").order_by(
        "school__name",
        "user__first_name",
        "user__last_name",
    )


def teaching_assignment_queryset():
    return TeachingAssignment.objects.select_related(
        "school",
        "class_section__academic_year",
        "subject",
        "teacher__user",
    ).order_by(
        "school__name",
        "class_section__academic_year__start_date",
        "class_section__grade_level",
        "class_section__stream",
        "subject__name",
    )


def enrollment_queryset():
    return Enrollment.objects.select_related(
        "school",
        "student__user",
        "class_section",
        "term",
    ).order_by(
        "school__name",
        "class_section__grade_level",
        "class_section__stream",
        "student__admission_number",
    )


def _should_hide_school_field(user):
    return bool(user and not user.is_superuser and user.school_id)


class ClassSectionForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = ClassSection
        fields = (
            "school",
            "academic_year",
            "grade_level",
            "stream",
            "capacity",
            "room_name",
            "homeroom_teacher",
            "notes",
        )
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if _should_hide_school_field(self.user):
            self.fields.pop("school")
            self.instance.school_id = self.user.school_id
        else:
            self.fields["school"].queryset = School.objects.order_by("name")
        self.fields["academic_year"].queryset = AcademicYear.objects.select_related("school").order_by(
            "school__name",
            "-start_date",
        )
        self.fields["homeroom_teacher"].queryset = teacher_queryset()
        self.apply_styles()


class SubjectForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Subject
        fields = (
            "school",
            "name",
            "code",
            "description",
            "is_optional",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if _should_hide_school_field(self.user):
            self.fields.pop("school")
            self.instance.school_id = self.user.school_id
        else:
            self.fields["school"].queryset = School.objects.order_by("name")
        self.apply_styles()


class TimetableEntryForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = TimetableEntry
        fields = (
            "school",
            "term",
            "teaching_assignment",
            "weekday",
            "start_time",
            "end_time",
            "room_name",
            "period_label",
            "notes",
        )
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.school = kwargs.pop("school", None)
        self.term = kwargs.pop("term", None)
        self.class_section = kwargs.pop("class_section", None)
        super().__init__(*args, **kwargs)

        if not self.school and _should_hide_school_field(self.user):
            self.school = self.user.school

        resolved_school = self.school or getattr(self.instance, "school", None)
        resolved_term = self.term or getattr(self.instance, "term", None)

        if _should_hide_school_field(self.user) and resolved_school:
            self.fields.pop("school")
            self.instance.school = resolved_school
        else:
            school_field = self.fields.get("school")
            if school_field:
                school_field.queryset = School.objects.order_by("name")
        self.fields["term"].queryset = Term.objects.select_related("school", "academic_year").order_by(
            "school__name",
            "academic_year__start_date",
            "start_date",
        )
        assignment_queryset = teaching_assignment_queryset()

        if resolved_school:
            if "school" in self.fields:
                self.fields["school"].queryset = School.objects.filter(pk=resolved_school.pk)
                self.fields["school"].initial = resolved_school
            self.fields["term"].queryset = self.fields["term"].queryset.filter(school=resolved_school)
            assignment_queryset = assignment_queryset.filter(school=resolved_school)

        if resolved_term:
            self.fields["term"].queryset = self.fields["term"].queryset.filter(pk=resolved_term.pk)
            self.fields["term"].initial = resolved_term
            assignment_queryset = assignment_queryset.filter(
                class_section__academic_year=resolved_term.academic_year
            )

        if self.class_section:
            assignment_queryset = assignment_queryset.filter(class_section=self.class_section)

        self.fields["teaching_assignment"].queryset = assignment_queryset
        self.apply_styles()


class GradeResultForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = GradeResult
        fields = (
            "enrollment",
            "subject",
            "exam_type",
            "score",
            "grade",
            "remarks",
            "result_document",
        )
        widgets = {
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

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

        enrollments = enrollment_queryset()
        subjects = subject_queryset()

        if resolved_school:
            enrollments = enrollments.filter(school=resolved_school)
            subjects = subjects.filter(school=resolved_school)
        if resolved_term:
            enrollments = enrollments.filter(term=resolved_term)
        if resolved_class_section:
            enrollments = enrollments.filter(class_section=resolved_class_section)

        if self.user and self.user.is_authenticated and not self.user.is_superuser:
            if self.user.school_id:
                enrollments = enrollments.filter(school_id=self.user.school_id)
                subjects = subjects.filter(school_id=self.user.school_id)
            if self.user.role == self.user.Role.TEACHER:
                assigned_class_ids = self.user.get_assigned_classes().values_list("id", flat=True)
                enrollments = enrollments.filter(class_section_id__in=assigned_class_ids)
                teacher_profile = self.user.get_teacher_profile()
                if teacher_profile:
                    assigned_subject_ids = teacher_profile.assigned_subjects.values_list("id", flat=True)
                    taught_subject_ids = teacher_profile.teaching_assignments.values_list("subject_id", flat=True)
                    subjects = subjects.filter(Q(pk__in=assigned_subject_ids) | Q(pk__in=taught_subject_ids))
                else:
                    subjects = subjects.none()

        self.fields["enrollment"].queryset = enrollments
        self.fields["subject"].queryset = subjects
        self.fields["exam_type"].required = False
        self.fields["exam_type"].initial = self.instance.exam_type or GradeResult.ExamType.END_TERM
        self.apply_styles()


class TeacherForm(UserBackedProfileFormMixin):
    target_role = User.Role.TEACHER

    class Meta:
        model = Teacher
        fields = (
            "school",
            "profile_photo",
            "employee_number",
            "tsc_number",
            "hire_date",
            "specialization",
            "assigned_classes",
            "assigned_subjects",
            "classes_in_charge",
            "qualification_document",
            "notes",
        )
        field_order = [
            "school",
            "first_name", "last_name", "username", "email", "phone",
            "profile_photo",
            "employee_number", "tsc_number", "hire_date", "specialization",
            "qualification_document",
            "assigned_classes", "assigned_subjects", "classes_in_charge",
            "password1", "password2", "is_active",
            "notes",
        ]
        widgets = {
            "hire_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "assigned_classes": forms.SelectMultiple(attrs={"size": "4"}),
            "assigned_subjects": forms.SelectMultiple(attrs={"size": "4"}),
            "classes_in_charge": forms.SelectMultiple(attrs={"size": "4"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if _should_hide_school_field(self.user):
            self.fields.pop("school", None)
            self.instance.school_id = self.user.school_id

        school_id = self.user.school_id if self.user else None
        if school_id:
            self.fields["assigned_classes"].queryset = ClassSection.objects.filter(
                school_id=school_id
            ).select_related("academic_year").order_by(
                "academic_year__start_date", "grade_level", "stream"
            )
            self.fields["assigned_subjects"].queryset = Subject.objects.filter(
                school_id=school_id
            ).order_by("name")
            self.fields["classes_in_charge"].queryset = ClassSection.objects.filter(
                school_id=school_id
            ).select_related("academic_year").order_by(
                "academic_year__start_date", "grade_level", "stream"
            )

    def clean(self):
        cleaned_data = super().clean()
        school = cleaned_data.get("school")
        employee_number = cleaned_data.get("employee_number", "").strip()
        tsc_number = cleaned_data.get("tsc_number", "").strip()
        if school and employee_number:
            queryset = Teacher.objects.filter(school=school, employee_number__iexact=employee_number)
            if getattr(self.instance, "pk", None):
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                self.add_error("employee_number", "A teacher with this employee number already exists in this school.")
        if school and tsc_number:
            queryset = Teacher.objects.filter(school=school, tsc_number__iexact=tsc_number)
            if getattr(self.instance, "pk", None):
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                self.add_error("tsc_number", "A teacher with this TSC number already exists in this school.")
        return cleaned_data


class ClassSectionFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())
    academic_year = forms.ModelChoiceField(required=False, queryset=AcademicYear.objects.none())

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        schools = School.objects.order_by("name")
        academic_years = AcademicYear.objects.select_related("school").order_by(
            "school__name",
            "-start_date",
        )
        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            if user_school:
                schools = schools.filter(pk=user_school.pk)
                academic_years = academic_years.filter(school=user_school)
            else:
                schools = schools.none()
                academic_years = academic_years.none()

        self.fields["school"].queryset = schools
        self.fields["academic_year"].queryset = academic_years
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type class, stream, room, teacher, or subject",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class SubjectFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())
    is_active = forms.ChoiceField(required=False, choices=BOOLEAN_FILTER_CHOICES)
    is_optional = forms.ChoiceField(required=False, choices=BOOLEAN_FILTER_CHOICES)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        schools = School.objects.order_by("name")
        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            schools = schools.filter(pk=user_school.pk) if user_school else schools.none()

        self.fields["school"].queryset = schools
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type subject name, code, or description",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class TimetableEntryFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())
    term = forms.ModelChoiceField(required=False, queryset=Term.objects.none())
    class_section = forms.ModelChoiceField(required=False, queryset=ClassSection.objects.none())
    subject = forms.ModelChoiceField(required=False, queryset=Subject.objects.none())
    teacher = forms.ModelChoiceField(required=False, queryset=Teacher.objects.none())
    weekday = forms.ChoiceField(
        required=False,
        choices=[("", "All weekdays"), *TimetableEntry.Weekday.choices],
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
        class_sections = section_queryset()
        subjects = subject_queryset()
        teachers = teacher_queryset()

        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            if user_school:
                schools = schools.filter(pk=user_school.pk)
                terms = terms.filter(school=user_school)
                class_sections = class_sections.filter(school=user_school)
                subjects = subjects.filter(school=user_school)
                teachers = teachers.filter(school=user_school)
            else:
                schools = schools.none()
                terms = terms.none()
                class_sections = class_sections.none()
                subjects = subjects.none()
                teachers = teachers.none()

        self.fields["school"].queryset = schools
        self.fields["term"].queryset = terms
        self.fields["class_section"].queryset = class_sections
        self.fields["subject"].queryset = subjects
        self.fields["teacher"].queryset = teachers
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type subject, class, teacher, room, or period",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class GradeResultFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())
    term = forms.ModelChoiceField(required=False, queryset=Term.objects.none())
    class_section = forms.ModelChoiceField(required=False, queryset=ClassSection.objects.none())
    subject = forms.ModelChoiceField(required=False, queryset=Subject.objects.none())
    exam_type = forms.ChoiceField(
        required=False,
        choices=[("", "All exam types"), *GradeResult.ExamType.choices],
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
        class_sections = section_queryset()
        subjects = subject_queryset()

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
                "placeholder": "Type student name, admission number, subject, or grade",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )