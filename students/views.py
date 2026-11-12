from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from core.authz import RolePermissionRequiredMixin
from core.encryption import fingerprint_value
from core.models import User
from core.scoping import SchoolScopeMixin
from core.school_scoping import SchoolScopedQuerysetMixin
from core.views_mixins import HtmxTemplateMixin, SuccessMessageFormMixin, htmx_redirect

from .forms import (
	EnrollmentForm,
	GuardianFilterForm,
	GuardianForm,
	StudentFilterForm,
	StudentForm,
	StudentGuardianRelationshipForm,
)
from .models import Enrollment, Guardian, Student, StudentGuardianRelationship


class StudentModuleReadMixin(RolePermissionRequiredMixin):
	allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)


class StudentModuleWriteMixin(RolePermissionRequiredMixin):
	allowed_roles = (User.Role.SCHOOL_ADMIN,)


class StudentListView(HtmxTemplateMixin, SchoolScopeMixin, StudentModuleReadMixin, ListView):
	model = Student
	template_name = "students/student_list.html"
	htmx_template_name = "students/partials/student_results.html"
	context_object_name = "students"
	paginate_by = 10
	permission_required = (
		"students.view_student",
		"students.view_guardian",
		"students.view_studentguardianrelationship",
		"students.view_enrollment",
	)

	def get_queryset(self):
		self.filter_form = StudentFilterForm(self.request.GET or None, user=self.request.user)
		queryset = Student.objects.for_user_visibility(self.request.user).select_related(
			"user", "school"
		).prefetch_related(
			Prefetch(
				"guardian_relationships",
				queryset=StudentGuardianRelationship.objects.select_related("guardian__user").order_by(
					"-is_primary_contact",
					"guardian__user__first_name",
					"guardian__user__last_name",
				),
			),
			Prefetch(
				"enrollments",
				queryset=Enrollment.objects.select_related("class_section", "term", "academic_year").order_by(
					"-start_date"
				),
			),
		)

		if self.filter_form.is_valid():
			query = self.filter_form.cleaned_data.get("q")
			school = self.filter_form.cleaned_data.get("school")
			status = self.filter_form.cleaned_data.get("status")
			class_section = self.filter_form.cleaned_data.get("class_section")

			if query:
				queryset = queryset.filter(
					Q(admission_number__icontains=query)
					| Q(user__username__icontains=query)
					| Q(user__first_name__icontains=query)
					| Q(user__last_name__icontains=query)
					| Q(user__email__icontains=query)
					| Q(guardian_relationships__guardian__user__first_name__icontains=query)
					| Q(guardian_relationships__guardian__user__last_name__icontains=query)
					| Q(guardian_relationships__guardian__user__email__icontains=query)
				)

			if school:
				queryset = queryset.filter(school=school)
			if status:
				queryset = queryset.filter(status=status)
			if class_section:
				queryset = queryset.filter(
					enrollments__class_section=class_section,
					enrollments__status=Enrollment.Status.ACTIVE,
				)

		return queryset.distinct()

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["filter_form"] = self.filter_form
		context["page_title"] = "Students"
		return context


class GuardianListView(HtmxTemplateMixin, SchoolScopeMixin, StudentModuleReadMixin, ListView):
	model = Guardian
	template_name = "students/guardian_list.html"
	htmx_template_name = "students/partials/guardian_results.html"
	context_object_name = "guardians"
	paginate_by = 10
	permission_required = (
		"students.view_guardian",
		"students.view_studentguardianrelationship",
		"students.view_student",
	)

	def get_queryset(self):
		self.filter_form = GuardianFilterForm(self.request.GET or None, user=self.request.user)
		queryset = Guardian.objects.select_related("user", "school").prefetch_related(
			Prefetch(
				"student_relationships",
				queryset=StudentGuardianRelationship.objects.select_related("student__user").order_by(
					"student__admission_number"
				),
			)
		)

		if self.filter_form.is_valid():
			query = self.filter_form.cleaned_data.get("q")
			school = self.filter_form.cleaned_data.get("school")

			if query:
				search_filter = (
					Q(user__username__icontains=query)
					| Q(user__first_name__icontains=query)
					| Q(user__last_name__icontains=query)
					| Q(user__email__icontains=query)
					| Q(student_relationships__student__admission_number__icontains=query)
					| Q(student_relationships__student__user__first_name__icontains=query)
					| Q(student_relationships__student__user__last_name__icontains=query)
				)
				national_id_fingerprint = fingerprint_value(query)
				if national_id_fingerprint:
					search_filter |= Q(national_id_fingerprint=national_id_fingerprint)
				queryset = queryset.filter(search_filter)
			if school:
				queryset = queryset.filter(school=school)

		visible_students = Student.objects.for_user_visibility(self.request.user)
		queryset = queryset.filter(student_relationships__student__in=visible_students)
		return queryset.distinct()

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["filter_form"] = self.filter_form
		context["page_title"] = "Parents & guardians"
		return context


class StudentDetailView(SchoolScopeMixin, StudentModuleReadMixin, DetailView):
	model = Student
	template_name = "students/student_detail.html"
	context_object_name = "student"
	permission_required = (
		"students.view_student",
		"students.view_guardian",
		"students.view_studentguardianrelationship",
		"students.view_enrollment",
	)

	def get_queryset(self):
		return Student.objects.for_user_visibility(self.request.user).select_related("user", "school").prefetch_related(
			Prefetch(
				"guardian_relationships",
				queryset=StudentGuardianRelationship.objects.select_related("guardian__user").order_by(
					"-is_primary_contact",
					"guardian__user__first_name",
					"guardian__user__last_name",
				),
			),
			Prefetch(
				"enrollments",
				queryset=Enrollment.objects.select_related("academic_year", "term", "class_section").order_by(
					"-start_date"
				),
			),
		)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["can_manage_student_records"] = self.request.user.has_perm("students.change_student")
		context["can_manage_guardian_links"] = self.request.user.has_perm(
			"students.add_studentguardianrelationship"
		)
		context["can_manage_enrollments"] = self.request.user.has_perm("students.add_enrollment")
		from cbc.models import CBCReport
		context["recent_cbc_reports"] = list(
			CBCReport.objects.filter(enrollment__student=self.object)
			.select_related("term__academic_year", "enrollment__class_section", "enrollment__student__user")
			.order_by("-term__start_date")[:3]
		)

		if context["can_manage_guardian_links"]:
			context["relationship_form"] = StudentGuardianRelationshipForm(student=self.object)
		if context["can_manage_enrollments"]:
			context["enrollment_form"] = EnrollmentForm(student=self.object, school=self.object.school)
		return context


class GuardianDetailView(SchoolScopeMixin, StudentModuleReadMixin, DetailView):
	model = Guardian
	template_name = "students/guardian_detail.html"
	context_object_name = "guardian"
	permission_required = (
		"students.view_guardian",
		"students.view_studentguardianrelationship",
		"students.view_student",
	)

	def get_queryset(self):
		visible_students = Student.objects.for_user_visibility(self.request.user)
		return Guardian.objects.filter(
			student_relationships__student__in=visible_students
		).select_related("user", "school").prefetch_related(
			Prefetch(
				"student_relationships",
				queryset=StudentGuardianRelationship.objects.select_related("student__user").order_by(
					"student__admission_number"
				),
			)
		).distinct()


class StudentCreateView(HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, CreateView):
	model = Student
	form_class = StudentForm
	template_name = "students/student_form.html"
	htmx_template_name = "students/partials/student_form_modal.html"
	permission_required = "students.add_student"
	success_message = "Student created successfully."

	def get_success_url(self):
		return reverse("students:student-detail", kwargs={"pk": self.object.pk})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["form_title"] = "Add New Student"
		context["submit_label"] = "Create Student"
		return context


class StudentUpdateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, UpdateView):
	# Student has a direct school FK.
	school_lookup = "school_id"
	model = Student
	form_class = StudentForm
	template_name = "students/student_form.html"
	htmx_template_name = "students/partials/student_form_modal.html"
	permission_required = "students.change_student"
	success_message = "Student updated successfully."

	def get_success_url(self):
		return reverse("students:student-detail", kwargs={"pk": self.object.pk})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["form_title"] = "Edit Student"
		context["submit_label"] = "Save Student"
		return context


class GuardianCreateView(HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, CreateView):
	model = Guardian
	form_class = GuardianForm
	template_name = "students/guardian_form.html"
	htmx_template_name = "students/partials/guardian_form_modal.html"
	permission_required = "students.add_guardian"
	success_message = "Guardian created successfully."

	def get_success_url(self):
		return reverse("students:guardian-detail", kwargs={"pk": self.object.pk})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["form_title"] = "Create guardian"
		context["submit_label"] = "Create guardian"
		return context


class GuardianUpdateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, UpdateView):
	# Guardian has a direct school FK.
	school_lookup = "school_id"
	model = Guardian
	form_class = GuardianForm
	template_name = "students/guardian_form.html"
	htmx_template_name = "students/partials/guardian_form_modal.html"
	permission_required = "students.change_guardian"
	success_message = "Guardian updated successfully."

	def get_success_url(self):
		return reverse("students:guardian-detail", kwargs={"pk": self.object.pk})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["form_title"] = "Update guardian"
		context["submit_label"] = "Save changes"
		return context


class StudentGuardianRelationshipCreateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, CreateView):
	model = StudentGuardianRelationship
	# dispatch() resolves the STUDENT the link attaches to (the SGR row
	# inherits the student's school), so the lookup is the Student path.
	school_lookup = "school_id"
	form_class = StudentGuardianRelationshipForm
	template_name = "students/relationship_form.html"
	htmx_template_name = "students/partials/relationship_form.html"
	permission_required = "students.add_studentguardianrelationship"
	success_message = "Guardian linked successfully."

	def dispatch(self, request, *args, **kwargs):
		# School-scoped: staff of another school cannot render the link form
		# for a student that is not theirs (404).
		self.student = get_object_or_404(
			self.scope_queryset_to_school(
				Student.objects.select_related("school", "user")
			),
			pk=kwargs["student_pk"],
		)
		return super().dispatch(request, *args, **kwargs)

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["student"] = self.student
		return kwargs

	def get_success_url(self):
		return reverse("students:student-detail", kwargs={"pk": self.student.pk})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["student"] = self.student
		context["form_title"] = f"Link guardian to {self.student}"
		return context


class StudentGuardianRelationshipUpdateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, UpdateView):
	# StudentGuardianRelationship -> student (students.Student) -> school
	school_lookup = "student__school_id"
	model = StudentGuardianRelationship
	form_class = StudentGuardianRelationshipForm
	template_name = "students/relationship_form.html"
	htmx_template_name = "students/partials/relationship_form.html"
	permission_required = "students.change_studentguardianrelationship"
	success_message = "Guardian link updated successfully."

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["student"] = self.object.student
		return kwargs

	def get_success_url(self):
		return reverse("students:student-detail", kwargs={"pk": self.object.student_id})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["student"] = self.object.student
		context["form_title"] = f"Update guardian link for {self.object.student}"
		return context


class StudentGuardianRelationshipDeleteView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, StudentModuleWriteMixin, DeleteView):
	# StudentGuardianRelationship -> student (students.Student) -> school
	school_lookup = "student__school_id"
	model = StudentGuardianRelationship
	template_name = "students/relationship_confirm_delete.html"
	htmx_template_name = "students/partials/relationship_confirm_delete.html"
	permission_required = "students.delete_studentguardianrelationship"

	def form_valid(self, form):
		student_id = self.object.student_id
		messages.success(self.request, "Guardian link removed successfully.")
		response = super().form_valid(form)
		success_url = reverse("students:student-detail", kwargs={"pk": student_id})
		if getattr(self.request, "htmx", False):
			return htmx_redirect(success_url)
		return response

	def get_success_url(self):
		return reverse("students:student-detail", kwargs={"pk": self.object.student_id})


class EnrollmentCreateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, CreateView):
	model = Enrollment
	# dispatch() resolves the STUDENT the enrollment attaches to, so the
	# lookup is the Student path (Student -> school).
	school_lookup = "school_id"
	form_class = EnrollmentForm
	template_name = "students/enrollment_form.html"
	htmx_template_name = "students/partials/enrollment_form.html"
	permission_required = "students.add_enrollment"
	success_message = "Enrollment created successfully."

	def dispatch(self, request, *args, **kwargs):
		# School-scoped: staff of another school cannot render the enrollment
		# form for a student that is not theirs (404).
		self.student = get_object_or_404(
			self.scope_queryset_to_school(
				Student.objects.select_related("school", "user")
			),
			pk=kwargs["student_pk"],
		)
		return super().dispatch(request, *args, **kwargs)

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["student"] = self.student
		kwargs["school"] = self.student.school
		return kwargs

	def get_initial(self):
		initial = super().get_initial()
		initial["school"] = self.student.school
		initial["student"] = self.student
		return initial

	def get_success_url(self):
		return reverse("students:student-detail", kwargs={"pk": self.student.pk})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["student"] = self.student
		context["form_title"] = f"Add enrollment for {self.student}"
		return context


class EnrollmentUpdateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, SuccessMessageFormMixin, StudentModuleWriteMixin, UpdateView):
	# Enrollment has a direct school FK.
	school_lookup = "school_id"
	model = Enrollment
	form_class = EnrollmentForm
	template_name = "students/enrollment_form.html"
	htmx_template_name = "students/partials/enrollment_form.html"
	permission_required = "students.change_enrollment"
	success_message = "Enrollment updated successfully."

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["student"] = self.object.student
		kwargs["school"] = self.object.school
		return kwargs

	def get_success_url(self):
		return reverse("students:student-detail", kwargs={"pk": self.object.student_id})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["student"] = self.object.student
		context["form_title"] = f"Update enrollment for {self.object.student}"
		return context


class DeletedStudentListView(HtmxTemplateMixin, SchoolScopeMixin, StudentModuleWriteMixin, ListView):
	model = Student
	template_name = "students/deleted_student_list.html"
	htmx_template_name = "students/partials/deleted_student_results.html"
	context_object_name = "students"
	paginate_by = 10
	permission_required = "students.view_student"

	def get_queryset(self):
		return Student.all_objects.deleted().select_related("user", "school").order_by("-deleted_at")

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["page_title"] = "Deleted students"
		return context


class DeletedGuardianListView(HtmxTemplateMixin, SchoolScopeMixin, StudentModuleWriteMixin, ListView):
	model = Guardian
	template_name = "students/deleted_guardian_list.html"
	htmx_template_name = "students/partials/deleted_guardian_results.html"
	context_object_name = "guardians"
	paginate_by = 10
	permission_required = "students.view_guardian"

	def get_queryset(self):
		return Guardian.all_objects.deleted().select_related("user", "school").order_by("-deleted_at")

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["page_title"] = "Deleted guardians"
		return context


class RestoreStudentView(SchoolScopedQuerysetMixin, StudentModuleWriteMixin, View):
	# Student has a direct school FK.
	school_lookup = "school_id"
	permission_required = "students.change_student"

	def post(self, request, *args, **kwargs):
		# School-scoped over all_objects (the row is soft-deleted); a
		# cross-school or unknown pk now 404s instead of restoring blindly.
		student = get_object_or_404(
			self.scope_queryset_to_school(
				Student.all_objects.select_related("user")
			),
			pk=kwargs["pk"],
		)
		student.deleted_at = None
		student.save(update_fields=["deleted_at", "updated_at"])
		messages.success(request, f"Student {student} restored successfully.")
		return HttpResponseRedirect(reverse("students:student-detail", kwargs={"pk": student.pk}))


class RestoreGuardianView(SchoolScopedQuerysetMixin, StudentModuleWriteMixin, View):
	# Guardian has a direct school FK.
	school_lookup = "school_id"
	permission_required = "students.change_guardian"

	def post(self, request, *args, **kwargs):
		# School-scoped over all_objects (the row is soft-deleted); a
		# cross-school or unknown pk now 404s instead of restoring blindly.
		guardian = get_object_or_404(
			self.scope_queryset_to_school(
				Guardian.all_objects.select_related("user")
			),
			pk=kwargs["pk"],
		)
		guardian.deleted_at = None
		guardian.save(update_fields=["deleted_at", "updated_at"])
		messages.success(request, f"Guardian {guardian} restored successfully.")
		return HttpResponseRedirect(reverse("students:guardian-detail", kwargs={"pk": guardian.pk}))
