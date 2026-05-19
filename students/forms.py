from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.db import transaction

from academics.models import AcademicYear, ClassSection, Term
from core.encryption import fingerprint_value
from core.models import School, User

from .models import Enrollment, Guardian, Student, StudentGuardianRelationship


INPUT_CLASS = (
    "block w-full border border-slate-300 bg-white px-3 py-2 "
    "text-sm text-slate-900 outline-none transition focus:border-sky-500 "
    "focus:ring-2 focus:ring-sky-200"
)
TEXTAREA_CLASS = (
    "block min-h-24 w-full border border-slate-300 bg-white px-3 py-2 "
    "text-sm text-slate-900 outline-none transition focus:border-sky-500 "
    "focus:ring-2 focus:ring-sky-200"
)
CHECKBOX_CLASS = "h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-sky-200"


class StyledFieldsMixin:
    def apply_styles(self):
        for field in self.fields.values():
            widget = field.widget

            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = TEXTAREA_CLASS
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = CHECKBOX_CLASS
            elif isinstance(widget, (forms.Select, forms.SelectMultiple, forms.ClearableFileInput, forms.FileInput)):
                widget.attrs["class"] = INPUT_CLASS
            else:
                widget.attrs["class"] = INPUT_CLASS

            if isinstance(widget, forms.DateInput):
                widget.attrs.setdefault("type", "date")


class UserBackedProfileFormMixin(StyledFieldsMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=16, required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    password1 = forms.CharField(
        label="Password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
    )
    password2 = forms.CharField(
        label="Confirm password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
    )

    target_role = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_instance = getattr(self.instance, "user", None)

        if self.user_instance:
            self.fields["first_name"].initial = self.user_instance.first_name
            self.fields["last_name"].initial = self.user_instance.last_name
            self.fields["username"].initial = self.user_instance.username
            self.fields["email"].initial = self.user_instance.email
            self.fields["phone"].initial = self.user_instance.phone
            self.fields["is_active"].initial = self.user_instance.is_active
            self.fields["password1"].help_text = "Leave blank to keep the current password."

        self.fields["school"].queryset = School.objects.order_by("name")
        self.apply_styles()

        # Reorder fields according to Meta.field_order (needed because mixin fields
        # are added dynamically and Django's built-in ordering doesn't catch them)
        field_order = getattr(getattr(self, "Meta", None), "field_order", None)
        if field_order:
            from collections import OrderedDict

            ordered = OrderedDict()
            for name in field_order:
                if name in self.fields:
                    ordered[name] = self.fields.pop(name)
            # Append any remaining fields not in field_order
            ordered.update(self.fields)
            self.fields = ordered

    def clean_username(self):
        username = self.cleaned_data["username"]
        queryset = User.objects.filter(username__iexact=username)
        if self.user_instance and self.user_instance.pk:
            queryset = queryset.exclude(pk=self.user_instance.pk)
        if queryset.exists():
            raise ValidationError("A user with that username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        queryset = User.objects.filter(email__iexact=email)
        if self.user_instance and self.user_instance.pk:
            queryset = queryset.exclude(pk=self.user_instance.pk)
        if queryset.exists():
            raise ValidationError("A user with that email address already exists.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not phone:
            return phone
        queryset = User.objects.filter(phone=phone)
        if self.user_instance and self.user_instance.pk:
            queryset = queryset.exclude(pk=self.user_instance.pk)
        if queryset.exists():
            raise ValidationError("A user with that phone number already exists.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if not self.user_instance and not password1:
            self.add_error("password1", "Password is required when creating a new account.")

        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "The two password fields must match.")
            else:
                candidate_user = self.user_instance or User(
                    username=cleaned_data.get("username", ""),
                    email=cleaned_data.get("email", ""),
                    first_name=cleaned_data.get("first_name", ""),
                    last_name=cleaned_data.get("last_name", ""),
                    role=self.target_role,
                )
                try:
                    password_validation.validate_password(password1, user=candidate_user)
                except ValidationError as exc:
                    self.add_error("password1", exc)

        # Prevent creating a duplicate profile for a user who already has one
        if self.target_role and not getattr(self.instance, "pk", None):
            email = cleaned_data.get("email", "").strip().lower()
            username = cleaned_data.get("username", "").strip()
            if email or username:
                existing_user = None
                if email:
                    existing_user = User.objects.filter(email__iexact=email).first()
                if not existing_user and username:
                    existing_user = User.objects.filter(username__iexact=username).first()
                if existing_user:
                    profile_attr = {
                        User.Role.STUDENT: "student_profile",
                        User.Role.TEACHER: "teacher_profile",
                        User.Role.PARENT: "guardian_profile",
                    }.get(self.target_role)
                    if profile_attr and hasattr(existing_user, profile_attr):
                        try:
                            profile = getattr(existing_user, profile_attr)
                            if profile and getattr(profile, "pk", None):
                                raise ValidationError(
                                    f"This person already exists as a {self.target_role.label.lower()} in the system."
                                )
                        except (Student.DoesNotExist, Guardian.DoesNotExist):
                            pass

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = self.user_instance or User(role=self.target_role)
        user.username = self.cleaned_data["username"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data["phone"]
        user.is_active = self.cleaned_data["is_active"]
        user.role = self.target_role

        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_unusable_password()

        if commit:
            user.save()

        instance = super().save(commit=False)
        instance.user = user

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class StudentForm(UserBackedProfileFormMixin):
    target_role = User.Role.STUDENT

    class Meta:
        model = Student
        fields = (
            "school",
            "admission_number",
            "date_of_birth",
            "gender",
            "admission_date",
            "status",
            "photo",
            "admission_document",
            "address",
            "notes",
        )
        field_order = [
            "school",
            "first_name", "last_name", "username", "email", "phone",
            "admission_number", "date_of_birth", "gender", "admission_date", "status",
            "photo", "admission_document", "address",
            "password1", "password2", "is_active",
            "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "admission_date": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        school = cleaned_data.get("school")
        admission_number = cleaned_data.get("admission_number", "").strip()
        if school and admission_number:
            queryset = Student.objects.filter(school=school, admission_number__iexact=admission_number)
            if getattr(self.instance, "pk", None):
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                self.add_error("admission_number", "A student with this admission number already exists in this school.")
        return cleaned_data


class GuardianForm(UserBackedProfileFormMixin):
    target_role = User.Role.PARENT

    class Meta:
        model = Guardian
        fields = (
            "school",
            "occupation",
            "national_id",
            "postal_address",
            "identification_document",
            "notes",
        )
        field_order = [
            "school",
            "first_name", "last_name", "username", "email", "phone",
            "occupation", "national_id", "postal_address",
            "identification_document",
            "password1", "password2", "is_active",
            "notes",
        ]
        widgets = {
            "national_id": forms.TextInput(),
            "postal_address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        school = cleaned_data.get("school")
        national_id = cleaned_data.get("national_id", "").strip()
        if school and national_id:
            fingerprint = fingerprint_value(national_id)
            if fingerprint:
                queryset = Guardian.objects.filter(school=school, national_id_fingerprint=fingerprint)
                if getattr(self.instance, "pk", None):
                    queryset = queryset.exclude(pk=self.instance.pk)
                if queryset.exists():
                    self.add_error("national_id", "A guardian with this national ID already exists in this school.")
        return cleaned_data


class StudentGuardianRelationshipForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = StudentGuardianRelationship
        fields = (
            "student",
            "guardian",
            "relationship",
            "is_primary_contact",
            "is_emergency_contact",
            "is_fee_payer",
            "notes",
        )
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.student = kwargs.pop("student", None)
        self.guardian = kwargs.pop("guardian", None)
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.select_related("user", "school").order_by(
            "school__name", "admission_number"
        )
        self.fields["guardian"].queryset = Guardian.objects.select_related("user", "school").order_by(
            "school__name", "user__first_name", "user__last_name"
        )

        if self.student:
            self.fields["student"].queryset = Student.objects.filter(pk=self.student.pk)
            self.fields["student"].initial = self.student
            self.fields["guardian"].queryset = self.fields["guardian"].queryset.filter(school=self.student.school)
        if self.guardian:
            self.fields["guardian"].queryset = Guardian.objects.filter(pk=self.guardian.pk)
            self.fields["guardian"].initial = self.guardian

        self.apply_styles()


class EnrollmentForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = (
            "school",
            "student",
            "academic_year",
            "term",
            "class_section",
            "status",
            "start_date",
            "end_date",
            "roll_number",
            "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.student = kwargs.pop("student", None)
        self.school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)

        self.fields["school"].queryset = School.objects.order_by("name")
        self.fields["student"].queryset = Student.objects.select_related("user", "school").order_by(
            "school__name", "admission_number"
        )
        self.fields["academic_year"].queryset = AcademicYear.objects.select_related("school").order_by(
            "school__name", "-start_date"
        )
        self.fields["term"].queryset = Term.objects.select_related("school", "academic_year").order_by(
            "school__name", "academic_year__start_date", "start_date"
        )
        self.fields["class_section"].queryset = ClassSection.objects.select_related(
            "school", "academic_year"
        ).order_by("school__name", "academic_year__start_date", "grade_level", "stream")

        locked_school = self.school or getattr(self.instance, "school", None)
        if self.student:
            self.fields["student"].queryset = Student.objects.filter(pk=self.student.pk)
            self.fields["student"].initial = self.student
            locked_school = locked_school or self.student.school

        if locked_school:
            self.fields["school"].queryset = School.objects.filter(pk=locked_school.pk)
            self.fields["school"].initial = locked_school
            self.fields["student"].queryset = self.fields["student"].queryset.filter(school=locked_school)
            self.fields["academic_year"].queryset = self.fields["academic_year"].queryset.filter(school=locked_school)
            self.fields["term"].queryset = self.fields["term"].queryset.filter(school=locked_school)
            self.fields["class_section"].queryset = self.fields["class_section"].queryset.filter(school=locked_school)

        self.apply_styles()


class StudentFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses"), *Student.Status.choices],
    )
    class_section = forms.ModelChoiceField(required=False, queryset=ClassSection.objects.none())

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        schools = School.objects.order_by("name")
        class_sections = ClassSection.objects.select_related("school", "academic_year").order_by(
            "school__name", "academic_year__start_date", "grade_level", "stream"
        )

        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            if user_school:
                schools = schools.filter(pk=user_school.pk)
                class_sections = class_sections.filter(school=user_school)
            else:
                schools = schools.none()
                class_sections = class_sections.none()

        self.fields["school"].queryset = schools
        self.fields["class_section"].queryset = class_sections
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type student name, admission number, email, or guardian",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )


class GuardianFilterForm(StyledFieldsMixin, forms.Form):
    q = forms.CharField(required=False, label="Search")
    school = forms.ModelChoiceField(required=False, queryset=School.objects.none())

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        schools = School.objects.order_by("name")
        if self.user and not self.user.is_superuser:
            user_school = getattr(self.user, "school", None)
            if user_school:
                schools = schools.filter(pk=user_school.pk)
            else:
                schools = schools.none()

        self.fields["school"].queryset = schools
        self.apply_styles()
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Type guardian, student, admission number, or email",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        )