from django import forms
from django.forms import inlineformset_factory

from cbc.models import (
    CBCAssessment,
    CBCCoreCompetency,
    CBCReport,
    CoreCompetency,
    Strand,
    SubStrand,
)


# ---------------------------------------------------------------------------
# Report-level forms
# ---------------------------------------------------------------------------

class CBCReportCreateForm(forms.ModelForm):
    """Used to create a fresh report from a teacher's perspective.

    The user picks an enrollment; the term is pre-derived from the enrollment
    so we keep the data model consistent with the unique (enrollment, term)
    constraint.
    """

    class Meta:
        model = CBCReport
        fields = ("enrollment",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["enrollment"].label = "Student enrollment"
        self.fields["enrollment"].queryset = self.fields["enrollment"].queryset.select_related(
            "student__user", "class_section", "term__academic_year"
        )
        self.fields["enrollment"].label_from_instance = self._label_enrollment

    @staticmethod
    def _label_enrollment(enrollment):
        student_name = enrollment.student.user.get_full_name() or enrollment.student.user.username
        return (
            f"{student_name} · {enrollment.student.admission_number} · "
            f"{enrollment.class_section.display_name} · {enrollment.term.get_name_display()}"
        )

    def save(self, commit=True):
        report = super().save(commit=False)
        report.term = report.enrollment.term
        if commit:
            report.save()
            report.snapshot_attendance()
            report.save(update_fields=["total_school_days", "days_present"])
        return report


class CBCReportRemarksForm(forms.ModelForm):
    class Meta:
        model = CBCReport
        fields = (
            "class_teacher_remarks",
            "head_teacher_remarks",
            "values_remarks",
            "general_remark",
        )
        widgets = {
            "class_teacher_remarks": forms.Textarea(attrs={"rows": 3, "class": "ksms-input"}),
            "head_teacher_remarks": forms.Textarea(attrs={"rows": 3, "class": "ksms-input"}),
            "values_remarks": forms.Textarea(attrs={"rows": 3, "class": "ksms-input"}),
            "general_remark": forms.Textarea(attrs={"rows": 2, "class": "ksms-input"}),
        }


# ---------------------------------------------------------------------------
# Inline formsets
# ---------------------------------------------------------------------------

class CBCAssessmentForm(forms.ModelForm):
    class Meta:
        model = CBCAssessment
        fields = ("subject", "strand", "sub_strand", "score", "remarks")
        widgets = {
            "subject": forms.Select(attrs={"class": "ksms-input"}),
            "strand": forms.Select(attrs={"class": "ksms-input"}),
            "sub_strand": forms.Select(attrs={"class": "ksms-input"}),
            "remarks": forms.TextInput(attrs={"class": "ksms-input"}),
            "score": forms.NumberInput(attrs={"class": "ksms-input", "min": 0, "max": 100, "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("subject", "strand", "sub_strand"):
            self.fields[field_name].required = False
        self.fields["score"].required = False

    def clean(self):
        cleaned_data = super().clean()
        subject = cleaned_data.get("subject")
        strand = cleaned_data.get("strand")
        sub_strand = cleaned_data.get("sub_strand")
        score = cleaned_data.get("score")
        remarks = cleaned_data.get("remarks")

        if not any((subject, strand, sub_strand, score, remarks)):
            return cleaned_data

        if not subject:
            self.add_error("subject", "Subject is required for an assessment row.")
        if score in (None, ""):
            self.add_error("score", "Score is required for an assessment row.")
        return cleaned_data


CBCAssessmentFormSet = inlineformset_factory(
    CBCReport,
    CBCAssessment,
    form=CBCAssessmentForm,
    extra=0,
    can_delete=True,
)


class CBCCoreCompetencyForm(forms.ModelForm):
    class Meta:
        model = CBCCoreCompetency
        fields = ("competency", "level", "remarks")
        widgets = {
            "competency": forms.Select(attrs={"class": "ksms-input"}),
            "level": forms.Select(attrs={"class": "ksms-input"}),
            "remarks": forms.TextInput(attrs={"class": "ksms-input"}),
        }


CBCCoreCompetencyFormSet = inlineformset_factory(
    CBCReport,
    CBCCoreCompetency,
    form=CBCCoreCompetencyForm,
    extra=0,
    can_delete=False,
    max_num=len(CoreCompetency.choices),
    validate_max=True,
)


# ---------------------------------------------------------------------------
# Strand catalog forms (admin only)
# ---------------------------------------------------------------------------

class StrandForm(forms.ModelForm):
    class Meta:
        model = Strand
        fields = ("subject", "grade_level", "name", "code", "order")
        widgets = {
            "subject": forms.Select(attrs={"class": "ksms-input"}),
            "grade_level": forms.TextInput(attrs={"class": "ksms-input"}),
            "name": forms.TextInput(attrs={"class": "ksms-input"}),
            "code": forms.TextInput(attrs={"class": "ksms-input"}),
            "order": forms.NumberInput(attrs={"class": "ksms-input", "min": 0}),
        }


class SubStrandForm(forms.ModelForm):
    class Meta:
        model = SubStrand
        fields = ("strand", "name", "code", "order")
        widgets = {
            "strand": forms.Select(attrs={"class": "ksms-input"}),
            "name": forms.TextInput(attrs={"class": "ksms-input"}),
            "code": forms.TextInput(attrs={"class": "ksms-input"}),
            "order": forms.NumberInput(attrs={"class": "ksms-input", "min": 0}),
        }
