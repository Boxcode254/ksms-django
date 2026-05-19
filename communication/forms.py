from django import forms

from core.models import School, User

from .models import Announcement


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


AUDIENCE_FILTER_CHOICES = [("", "All audiences")] + list(Announcement.Audience.choices)
ACTIVE_FILTER_CHOICES = [("", "All"), ("true", "Active"), ("false", "Inactive")]


class AnnouncementFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    audience = forms.ChoiceField(
        required=False,
        choices=AUDIENCE_FILTER_CHOICES,
        label="Audience",
    )
    is_active = forms.ChoiceField(
        required=False,
        choices=ACTIVE_FILTER_CHOICES,
        label="Status",
    )
    school = forms.ModelChoiceField(
        required=False,
        queryset=School.objects.none(),
        label="School",
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user and self.user.role in {User.Role.STUDENT, User.Role.PARENT}:
            self.fields.pop("audience", None)

        schools = School.objects.order_by("name")
        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            schools = schools.filter(pk=user_school.pk) if user_school else schools.none()

        self.fields["school"].queryset = schools
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type title, body, or author name",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class AnnouncementForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ("school", "title", "body", "audience", "is_active")
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school"].queryset = School.objects.order_by("name")
        self.apply_styles()
