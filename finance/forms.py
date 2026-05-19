from django import forms

from academics.models import AcademicYear, ClassSection, Term
from core.models import School, User
from students.models import Enrollment

from .models import FeeStructure, Invoice, Payment, ReminderPolicy


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

STATUS_FILTER_CHOICES = [("", "All statuses")] + list(Invoice.Status.choices)
METHOD_FILTER_CHOICES = [("", "All methods")] + list(Payment.Method.choices)
PAYMENT_STATUS_FILTER_CHOICES = [("", "All statuses")] + list(Payment.Status.choices)
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
            if isinstance(widget, forms.DateTimeInput):
                widget.attrs.setdefault("type", "datetime-local")


# ---------------------------------------------------------------------------
# Filter forms
# ---------------------------------------------------------------------------

class FeeStructureFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none(), label="School")
    academic_year = forms.ModelChoiceField(required=False, queryset=AcademicYear.objects.none(), label="Academic year")
    term = forms.ModelChoiceField(required=False, queryset=Term.objects.none(), label="Term")
    class_section = forms.ModelChoiceField(required=False, queryset=ClassSection.objects.none(), label="Class section")
    is_active = forms.ChoiceField(required=False, choices=BOOLEAN_FILTER_CHOICES, label="Active")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        schools = School.objects.order_by("name")
        academic_years = AcademicYear.objects.select_related("school").order_by(
            "school__name", "-start_date"
        )
        terms = Term.objects.select_related("school", "academic_year").order_by(
            "school__name", "academic_year__start_date", "start_date"
        )
        class_sections = ClassSection.objects.select_related(
            "school", "academic_year"
        ).order_by("school__name", "academic_year__start_date", "grade_level", "stream")

        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            if user_school:
                schools = schools.filter(pk=user_school.pk)
                academic_years = academic_years.filter(school=user_school)
                terms = terms.filter(school=user_school)
                class_sections = class_sections.filter(school=user_school)
            else:
                schools = schools.none()
                academic_years = academic_years.none()
                terms = terms.none()
                class_sections = class_sections.none()

        self.fields["school"].queryset = schools
        self.fields["academic_year"].queryset = academic_years
        self.fields["term"].queryset = terms
        self.fields["class_section"].queryset = class_sections
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type fee name, description, school, or class",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class InvoiceFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    status = forms.ChoiceField(required=False, choices=STATUS_FILTER_CHOICES, label="Status")
    term = forms.ModelChoiceField(required=False, queryset=Term.objects.none(), label="Term")
    class_section = forms.ModelChoiceField(required=False, queryset=ClassSection.objects.none(), label="Class section")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["term"].queryset = Term.objects.select_related("school", "academic_year").order_by(
            "school__name", "academic_year__start_date", "start_date"
        )
        self.fields["class_section"].queryset = ClassSection.objects.select_related(
            "school", "academic_year"
        ).order_by("school__name", "academic_year__start_date", "grade_level", "stream")
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type invoice number, student name, or admission number",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class PaymentFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    payment_method = forms.ChoiceField(required=False, choices=METHOD_FILTER_CHOICES, label="Method")
    status = forms.ChoiceField(required=False, choices=PAYMENT_STATUS_FILTER_CHOICES, label="Status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


# ---------------------------------------------------------------------------
# Model forms (admin write)
# ---------------------------------------------------------------------------

class FeeStructureForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = (
            "school",
            "academic_year",
            "term",
            "class_section",
            "name",
            "description",
            "amount",
            "due_date",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school"].queryset = School.objects.order_by("name")
        self.fields["academic_year"].queryset = AcademicYear.objects.select_related("school").order_by(
            "school__name", "-start_date"
        )
        self.fields["term"].queryset = Term.objects.select_related("school", "academic_year").order_by(
            "school__name", "academic_year__start_date", "start_date"
        )
        self.fields["class_section"].queryset = ClassSection.objects.select_related(
            "school", "academic_year"
        ).order_by("school__name", "academic_year__start_date", "grade_level", "stream")
        self.apply_styles()


class InvoiceForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Invoice
        fields = (
            "enrollment",
            "fee_structure",
            "amount_due",
            "due_date",
            "notes",
        )
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["enrollment"].queryset = Enrollment.objects.select_related(
            "school",
            "student__user",
            "class_section",
            "term",
        ).order_by("school__name", "class_section__grade_level", "class_section__stream", "student__admission_number")
        self.fields["fee_structure"].queryset = FeeStructure.objects.select_related(
            "school", "term", "class_section"
        ).filter(is_active=True).order_by("school__name", "term__start_date", "name")
        self.apply_styles()


class PaymentForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = (
            "amount",
            "payment_method",
            "status",
            "paid_at",
            "received_by",
            "mpesa_receipt_number",
            "mpesa_phone_number",
            "notes",
        )
        widgets = {
            "paid_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["received_by"].queryset = User.objects.filter(
            role__in=[User.Role.SCHOOL_ADMIN]
        ).order_by("first_name", "last_name")
        self.fields["received_by"].required = False
        self.apply_styles()


class ReminderPolicyForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = ReminderPolicy
        fields = (
            "daily_enabled",
            "weekly_enabled",
            "email_enabled",
            "overdue_threshold_days",
            "min_hours_between_sends",
            "send_window_start",
            "send_window_end",
        )
        widgets = {
            "send_window_start": forms.TimeInput(attrs={"type": "time"}),
            "send_window_end": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean(self):
        cleaned_data = super().clean()
        window_start = cleaned_data.get("send_window_start")
        window_end = cleaned_data.get("send_window_end")

        if bool(window_start) ^ bool(window_end):
            raise forms.ValidationError("Provide both send window start and end times, or leave both blank.")

        if window_start and window_end:
            if window_start == window_end:
                raise forms.ValidationError("Send window start and end cannot be the same time.")
            if window_start > window_end:
                raise forms.ValidationError("Send window end must be later than start time.")

        return cleaned_data
