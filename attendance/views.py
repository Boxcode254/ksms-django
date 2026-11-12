import datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from academics.models import ClassSection, Subject, Term
from core.authz import RolePermissionRequiredMixin
from core.models import School, User
from core.school_scoping import SchoolScopedQuerysetMixin
from core.views_mixins import HtmxTemplateMixin, SuccessMessageFormMixin, htmx_redirect
from students.models import Enrollment

from .forms import (
	DailyAttendanceForm,
	PeriodAttendanceFilterForm,
	PeriodAttendanceForm,
)
from .models import AttendanceStatus, DailyAttendance, PeriodAttendance


class AttendanceModuleReadMixin(RolePermissionRequiredMixin):
	allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)


class AttendanceModuleWriteMixin(RolePermissionRequiredMixin):
	allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)


class AttendanceScopedAccessMixin:
	def _teacher_class_ids(self):
		return self.request.user.get_assigned_classes().values_list("id", flat=True)

	def _scope_queryset_for_user(self, queryset):
		user = self.request.user
		if user.is_superuser:
			return queryset
		if not user.school_id:
			return queryset.none()
		if user.school_id:
			queryset = queryset.filter(enrollment__school_id=user.school_id)
		if user.role == User.Role.TEACHER:
			queryset = queryset.filter(enrollment__class_section_id__in=self._teacher_class_ids())
		return queryset

	def _validate_daily_write_permission(self, *, enrollment):
		if not self.request.user.can_mark_class_register(enrollment.class_section):
			raise PermissionDenied("You are not allowed to mark the official class register for this class.")

	def _validate_period_write_permission(self, *, enrollment, subject):
		if not self.request.user.can_teach_subject_in_class(
			class_section=enrollment.class_section,
			subject=subject,
		):
			raise PermissionDenied("You are not allowed to mark period attendance for this class and subject.")


class AttendanceListContextMixin:
	page_title = ""
	create_url_name = ""
	status_model = AttendanceStatus

	def get_summary(self, queryset):
		return [
			{
				"value": value,
				"label": label,
				"count": queryset.filter(status=value).count(),
			}
			for value, label in self.status_model.choices
		]

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["filter_form"] = self.filter_form
		context["page_title"] = self.page_title
		context["create_url"] = reverse(self.create_url_name)
		context["status_summary"] = self.get_summary(self.object_list)
		return context


class TakeAttendanceView(HtmxTemplateMixin, AttendanceScopedAccessMixin, AttendanceModuleReadMixin, TemplateView):
	template_name = "attendance/take_attendance.html"
	htmx_template_name = "attendance/partials/take_attendance_content.html"
	permission_required = ("attendance.view_dailyattendance", "students.view_enrollment")
	allowed_statuses = (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT, AttendanceStatus.LATE)

	def _parse_attendance_date(self):
		raw = (self.request.GET.get("attendance_date") or self.request.POST.get("attendance_date") or "").strip()
		if raw:
			try:
				return datetime.date.fromisoformat(raw)
			except ValueError:
				return timezone.localdate()
		return timezone.localdate()

	def _get_accessible_classes(self):
		user = self.request.user
		queryset = ClassSection.objects.select_related("school", "academic_year", "homeroom_teacher__user")
		if user.is_superuser:
			return queryset.order_by("school__name", "grade_level", "stream")
		if not user.school_id:
			return queryset.none()
		if user.role == User.Role.SCHOOL_ADMIN:
			return queryset.filter(school_id=user.school_id).order_by("grade_level", "stream")
		assigned_ids = list(user.get_assigned_classes().values_list("id", flat=True))
		if not assigned_ids:
			return queryset.none()
		return queryset.filter(school_id=user.school_id, id__in=assigned_ids).order_by("grade_level", "stream")

	def _resolve_selected_class(self, classes_qs):
		requested_id = (self.request.GET.get("class_section") or self.request.POST.get("class_section") or "").strip()
		if requested_id:
			selected = classes_qs.filter(pk=requested_id).first()
			if selected:
				return selected, False
			return None, True
		return classes_qs.first(), False

	def _get_class_enrollments(self, class_section, query):
		if not class_section:
			return Enrollment.objects.none()
		queryset = Enrollment.objects.select_related(
			"student__user",
			"class_section",
			"school",
		).filter(
			class_section=class_section,
			status=Enrollment.Status.ACTIVE,
		)
		if query:
			queryset = queryset.filter(
				Q(student__admission_number__icontains=query)
				| Q(student__user__first_name__icontains=query)
				| Q(student__user__last_name__icontains=query)
			)
		return queryset.order_by("student__admission_number")

	def _existing_attendance_map(self, class_section, attendance_date):
		if not class_section:
			return {}
		records = DailyAttendance.objects.filter(
			enrollment__class_section=class_section,
			attendance_date=attendance_date,
		).only("enrollment_id", "status")
		return {record.enrollment_id: record.status for record in records}

	def _build_context(self):
		classes_qs = self._get_accessible_classes()
		selected_class, class_forbidden = self._resolve_selected_class(classes_qs)
		attendance_date = self._parse_attendance_date()
		query = (self.request.GET.get("q") or "").strip()

		can_submit_register = False
		if selected_class:
			can_submit_register = self.request.user.is_superuser or self.request.user.is_school_admin_role or self.request.user.can_mark_class_register(selected_class)

		students = self._get_class_enrollments(selected_class, query)
		attendance_map = self._existing_attendance_map(selected_class, attendance_date)

		present_count = sum(1 for status in attendance_map.values() if status == AttendanceStatus.PRESENT)
		absent_count = sum(1 for status in attendance_map.values() if status == AttendanceStatus.ABSENT)
		late_count = sum(1 for status in attendance_map.values() if status == AttendanceStatus.LATE)

		no_classes_message = None
		if not classes_qs.exists() and self.request.user.role == User.Role.TEACHER:
			no_classes_message = "No assigned classes found for your account."

		access_warning = None
		if class_forbidden:
			access_warning = "You can only access classes assigned to your account."

		return {
			"classes": classes_qs,
			"selected_class": selected_class,
			"attendance_date": attendance_date,
			"students": students,
			"attendance_map": attendance_map,
			"present_count": present_count,
			"absent_count": absent_count,
			"late_count": late_count,
			"can_submit_register": can_submit_register,
			"can_mark_official_register": can_submit_register,
			"allowed_statuses": self.allowed_statuses,
			"query": query,
			"show_success_toast": self.request.GET.get("saved") == "1",
			"no_classes_message": no_classes_message,
			"access_warning": access_warning,
		}

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context.update(self._build_context())
		return context

	@transaction.atomic
	def post(self, request, *args, **kwargs):
		classes_qs = self._get_accessible_classes()
		selected_class, class_forbidden = self._resolve_selected_class(classes_qs)
		if class_forbidden or not selected_class:
			raise PermissionDenied("You are not allowed to mark attendance for this class.")

		if not (request.user.is_superuser or request.user.is_school_admin_role or request.user.can_mark_class_register(selected_class)):
			raise PermissionDenied("Only school admins and class teachers can submit the official class register.")

		attendance_date = self._parse_attendance_date()
		enrollments = Enrollment.objects.filter(
			class_section=selected_class,
			status=Enrollment.Status.ACTIVE,
		).only("id")
		enrollment_ids = set(enrollments.values_list("id", flat=True))

		saved_count = 0
		for key, value in request.POST.items():
			if not key.startswith("status_"):
				continue
			status_value = (value or "").strip().lower()
			if status_value not in self.allowed_statuses:
				continue
			try:
				enrollment_id = int(key.replace("status_", "", 1))
			except ValueError:
				continue
			if enrollment_id not in enrollment_ids:
				continue

			DailyAttendance.objects.update_or_create(
				enrollment_id=enrollment_id,
				attendance_date=attendance_date,
				defaults={
					"status": status_value,
					"recorded_by": request.user,
				},
			)
			saved_count += 1

		messages.success(request, f"Attendance saved for {saved_count} learners.")
		return HttpResponseRedirect(
			f"{reverse('attendance:daily-list')}?class_section={selected_class.pk}&attendance_date={attendance_date.isoformat()}&saved=1"
		)


# Backward-compatible symbol for integrations importing the old class name.
DailyAttendanceListView = TakeAttendanceView


class PeriodAttendanceListView(HtmxTemplateMixin, AttendanceScopedAccessMixin, AttendanceListContextMixin, AttendanceModuleReadMixin, ListView):
	model = PeriodAttendance
	template_name = "attendance/period_list.html"
	htmx_template_name = "attendance/partials/period_results.html"
	context_object_name = "records"
	paginate_by = 20
	page_title = "Period attendance"
	create_url_name = "attendance:period-create"
	permission_required = ("attendance.view_periodattendance", "students.view_enrollment")

	def get_queryset(self):
		self.filter_form = PeriodAttendanceFilterForm(self.request.GET or None, user=self.request.user)
		queryset = PeriodAttendance.objects.select_related(
			"enrollment__student__user",
			"enrollment__class_section",
			"enrollment__term",
			"enrollment__school",
			"recorded_by",
			"subject",
		)

		if self.filter_form.is_valid():
			query = self.filter_form.cleaned_data.get("q")
			school = self.filter_form.cleaned_data.get("school")
			term = self.filter_form.cleaned_data.get("term")
			class_section = self.filter_form.cleaned_data.get("class_section")
			subject = self.filter_form.cleaned_data.get("subject")
			attendance_date = self.filter_form.cleaned_data.get("attendance_date")
			period_number = self.filter_form.cleaned_data.get("period_number")
			status = self.filter_form.cleaned_data.get("status")

			if query:
				queryset = queryset.filter(
					Q(enrollment__student__admission_number__icontains=query)
					| Q(enrollment__student__user__first_name__icontains=query)
					| Q(enrollment__student__user__last_name__icontains=query)
					| Q(enrollment__class_section__grade_level__icontains=query)
					| Q(enrollment__class_section__stream__icontains=query)
					| Q(subject__name__icontains=query)
					| Q(subject__code__icontains=query)
				)
			if school:
				queryset = queryset.filter(enrollment__school=school)
			if term:
				queryset = queryset.filter(enrollment__term=term)
			if class_section:
				queryset = queryset.filter(enrollment__class_section=class_section)
			if subject:
				queryset = queryset.filter(subject=subject)
			if attendance_date:
				queryset = queryset.filter(attendance_date=attendance_date)
			if period_number:
				queryset = queryset.filter(period_number=period_number)
			if status:
				queryset = queryset.filter(status=status)

		return self._scope_queryset_for_user(queryset)


class AttendanceFormContextMixin(AttendanceScopedAccessMixin):
	form_title = ""
	submit_label = ""
	list_url_name = ""

	def resolve_school(self):
		school_id = self.request.GET.get("school")
		return School.objects.filter(pk=school_id).first() if school_id else None

	def resolve_term(self):
		term_id = self.request.GET.get("term")
		return Term.objects.filter(pk=term_id).first() if term_id else None

	def resolve_class_section(self):
		class_section_id = self.request.GET.get("class_section")
		return ClassSection.objects.filter(pk=class_section_id).first() if class_section_id else None

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["school"] = self.resolve_school()
		kwargs["term"] = self.resolve_term()
		kwargs["class_section"] = self.resolve_class_section()
		kwargs["user"] = self.request.user
		return kwargs

	def get_initial(self):
		initial = super().get_initial()
		if self.request.GET.get("attendance_date"):
			initial["attendance_date"] = self.request.GET["attendance_date"]
		return initial

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["form_title"] = self.form_title
		context["submit_label"] = self.submit_label
		context["cancel_url"] = reverse(self.list_url_name)
		return context

	def _resolve_post_enrollment(self):
		enrollment_id = self.request.POST.get("enrollment")
		if not enrollment_id:
			return None
		return Enrollment.objects.select_related("class_section", "school").filter(pk=enrollment_id).first()

	def _resolve_post_subject(self):
		subject_id = self.request.POST.get("subject")
		if not subject_id:
			return None
		return Subject.objects.select_related("school").filter(pk=subject_id).first()


class DailyAttendanceCreateView(AttendanceFormContextMixin, SuccessMessageFormMixin, AttendanceModuleWriteMixin, CreateView):
	model = DailyAttendance
	form_class = DailyAttendanceForm
	template_name = "attendance/daily_form.html"
	permission_required = "attendance.add_dailyattendance"
	form_title = "Record daily attendance"
	submit_label = "Save daily attendance"
	list_url_name = "attendance:daily-list"
	success_message = "Daily attendance saved successfully."

	def post(self, request, *args, **kwargs):
		enrollment = self._resolve_post_enrollment()
		if enrollment and request.user.role == User.Role.TEACHER:
			self._validate_daily_write_permission(enrollment=enrollment)
		return super().post(request, *args, **kwargs)

	def form_valid(self, form):
		self._validate_daily_write_permission(enrollment=form.instance.enrollment)
		form.instance.recorded_by = self.request.user
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("attendance:daily-list")


class DailyAttendanceUpdateView(SchoolScopedQuerysetMixin, AttendanceFormContextMixin, SuccessMessageFormMixin, AttendanceModuleWriteMixin, UpdateView):
	# DailyAttendance -> enrollment (students.Enrollment) -> school
	school_lookup = "enrollment__school_id"
	model = DailyAttendance
	form_class = DailyAttendanceForm
	template_name = "attendance/daily_form.html"
	permission_required = "attendance.change_dailyattendance"
	form_title = "Update daily attendance"
	submit_label = "Update daily attendance"
	list_url_name = "attendance:daily-list"
	success_message = "Daily attendance updated successfully."

	def post(self, request, *args, **kwargs):
		enrollment = self._resolve_post_enrollment()
		if enrollment and request.user.role == User.Role.TEACHER:
			self._validate_daily_write_permission(enrollment=enrollment)
		return super().post(request, *args, **kwargs)

	def form_valid(self, form):
		self._validate_daily_write_permission(enrollment=form.instance.enrollment)
		form.instance.recorded_by = self.request.user
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("attendance:daily-list")


class PeriodAttendanceCreateView(AttendanceFormContextMixin, SuccessMessageFormMixin, AttendanceModuleWriteMixin, CreateView):
	model = PeriodAttendance
	form_class = PeriodAttendanceForm
	template_name = "attendance/period_form.html"
	permission_required = "attendance.add_periodattendance"
	form_title = "Record period attendance"
	submit_label = "Save period attendance"
	list_url_name = "attendance:period-list"
	success_message = "Period attendance saved successfully."

	def post(self, request, *args, **kwargs):
		enrollment = self._resolve_post_enrollment()
		subject = self._resolve_post_subject()
		if enrollment and subject and request.user.role == User.Role.TEACHER:
			self._validate_period_write_permission(enrollment=enrollment, subject=subject)
		return super().post(request, *args, **kwargs)

	def form_valid(self, form):
		self._validate_period_write_permission(
			enrollment=form.instance.enrollment,
			subject=form.instance.subject,
		)
		form.instance.recorded_by = self.request.user
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("attendance:period-list")


class PeriodAttendanceUpdateView(SchoolScopedQuerysetMixin, AttendanceFormContextMixin, SuccessMessageFormMixin, AttendanceModuleWriteMixin, UpdateView):
	# PeriodAttendance -> enrollment (students.Enrollment) -> school
	school_lookup = "enrollment__school_id"
	model = PeriodAttendance
	form_class = PeriodAttendanceForm
	template_name = "attendance/period_form.html"
	permission_required = "attendance.change_periodattendance"
	form_title = "Update period attendance"
	submit_label = "Update period attendance"
	list_url_name = "attendance:period-list"
	success_message = "Period attendance updated successfully."

	def post(self, request, *args, **kwargs):
		enrollment = self._resolve_post_enrollment()
		subject = self._resolve_post_subject()
		if enrollment and subject and request.user.role == User.Role.TEACHER:
			self._validate_period_write_permission(enrollment=enrollment, subject=subject)
		return super().post(request, *args, **kwargs)

	def form_valid(self, form):
		self._validate_period_write_permission(
			enrollment=form.instance.enrollment,
			subject=form.instance.subject,
		)
		form.instance.recorded_by = self.request.user
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("attendance:period-list")
