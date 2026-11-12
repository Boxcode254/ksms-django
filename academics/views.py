from collections import defaultdict

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.authz import RolePermissionRequiredMixin
from core.models import User
from core.school_scoping import SchoolScopedQuerysetMixin
from students.models import Enrollment

from .forms import (
	ClassSectionFilterForm,
	ClassSectionForm,
	GradeResultFilterForm,
	GradeResultForm,
	SubjectFilterForm,
	SubjectForm,
	TeacherForm,
	TimetableEntryFilterForm,
	TimetableEntryForm,
)
from .models import ClassSection, GradeResult, Subject, Teacher, TeachingAssignment, TimetableEntry


def htmx_redirect(redirect_to):
	response = HttpResponse(status=204)
	response["HX-Redirect"] = redirect_to
	return response


class HtmxTemplateMixin:
	htmx_template_name = None

	def get_template_names(self):
		htmx = getattr(self.request, "htmx", None)
		is_boosted = bool(getattr(htmx, "boosted", False))
		if htmx and not is_boosted and self.htmx_template_name:
			return [self.htmx_template_name]
		return [self.template_name]


class SuccessMessageFormMixin:
	success_message = ""

	def form_valid(self, form):
		self.object = form.save()
		if self.success_message:
			messages.success(self.request, self.success_message)
		if getattr(self.request, "htmx", False):
			return htmx_redirect(self.get_success_url())
		return HttpResponseRedirect(self.get_success_url())


class AcademicModuleReadMixin(RolePermissionRequiredMixin):
	allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)


class AcademicModuleAdminWriteMixin(RolePermissionRequiredMixin):
	allowed_roles = (User.Role.SCHOOL_ADMIN,)


class AcademicGradeWriteMixin(RolePermissionRequiredMixin):
	allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)


class AcademicScopedAccessMixin:
	def _teacher_class_ids(self):
		return self.request.user.get_assigned_classes().values_list("id", flat=True)

	def _teacher_subject_ids(self):
		teacher_profile = self.request.user.get_teacher_profile()
		if not teacher_profile:
			return Subject.objects.none().values_list("id", flat=True)
		assigned_ids = teacher_profile.assigned_subjects.values_list("id", flat=True)
		taught_ids = TeachingAssignment.objects.filter(
			teacher=teacher_profile,
			school_id=self.request.user.school_id,
		).values_list("subject_id", flat=True)
		return Subject.objects.filter(Q(pk__in=assigned_ids) | Q(pk__in=taught_ids)).values_list("id", flat=True)

	def _scope_school_queryset(self, queryset, *, school_lookup):
		user = self.request.user
		if user.is_superuser:
			return queryset
		if not user.school_id:
			return queryset.none()
		if user.school_id:
			queryset = queryset.filter(**{school_lookup: user.school_id})
		if user.role == User.Role.TEACHER:
			queryset = self._scope_teacher_queryset(queryset)
		return queryset

	def _scope_teacher_queryset(self, queryset):
		return queryset

	def _validate_grade_write_permission(self, *, enrollment, subject):
		if not self.request.user.can_teach_subject_in_class(
			class_section=enrollment.class_section,
			subject=subject,
		):
			raise PermissionDenied("You are not allowed to record grades for this class and subject.")


class AcademicListContextMixin:
	page_title = ""
	create_url_name = ""

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["filter_form"] = self.filter_form
		context["page_title"] = self.page_title
		context["create_url"] = reverse(self.create_url_name) if self.create_url_name else ""
		return context


class AcademicFormContextMixin:
	form_title = ""
	submit_label = ""
	list_url_name = ""

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["form_title"] = self.form_title
		context["submit_label"] = self.submit_label
		context["cancel_url"] = reverse(self.list_url_name)
		return context



class AcademicFormUserKwargsMixin:
	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["user"] = self.request.user
		return kwargs


# Used by forms that accept school/term/class_section constructor kwargs (Timetable, Grade)
class FilteredFormKwargsMixin:
	def _resolve_school(self):
		school_id = self.request.GET.get("school")
		from core.models import School
		return School.objects.filter(pk=school_id).first() if school_id else None

	def _resolve_term(self):
		term_id = self.request.GET.get("term")
		from .models import Term
		return Term.objects.filter(pk=term_id).first() if term_id else None

	def _resolve_class_section(self):
		cs_id = self.request.GET.get("class_section")
		return ClassSection.objects.filter(pk=cs_id).first() if cs_id else None

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["school"] = self._resolve_school()
		kwargs["term"] = self._resolve_term()
		kwargs["class_section"] = self._resolve_class_section()
		return kwargs


class ClassSectionListView(HtmxTemplateMixin, AcademicScopedAccessMixin, AcademicListContextMixin, AcademicModuleReadMixin, ListView):
	model = ClassSection
	template_name = "academics/classsection_list.html"
	htmx_template_name = "academics/partials/classsection_results.html"
	context_object_name = "sections"
	paginate_by = 12
	page_title = "Classes"
	create_url_name = "academics:classsection-create"
	permission_required = "academics.view_classsection"

	def get_queryset(self):
		self.filter_form = ClassSectionFilterForm(self.request.GET or None, user=self.request.user)
		queryset = ClassSection.objects.select_related(
			"school",
			"academic_year",
			"homeroom_teacher__user",
		).annotate(
			active_enrollment_count=Count(
				"enrollments",
				filter=Q(enrollments__status=Enrollment.Status.ACTIVE),
				distinct=True,
			),
		).prefetch_related(
			Prefetch(
				"teaching_assignments",
				queryset=TeachingAssignment.objects.select_related(
					"subject",
					"teacher__user",
				).order_by("subject__name"),
			),
		)

		if self.filter_form.is_valid():
			query = self.filter_form.cleaned_data.get("q")
			school = self.filter_form.cleaned_data.get("school")
			academic_year = self.filter_form.cleaned_data.get("academic_year")

			if query:
				queryset = queryset.filter(
					Q(grade_level__icontains=query)
					| Q(stream__icontains=query)
					| Q(room_name__icontains=query)
					| Q(homeroom_teacher__user__first_name__icontains=query)
					| Q(homeroom_teacher__user__last_name__icontains=query)
					| Q(teaching_assignments__subject__name__icontains=query)
				)
			if school:
				queryset = queryset.filter(school=school)
			if academic_year:
				queryset = queryset.filter(academic_year=academic_year)

		queryset = self._scope_school_queryset(queryset, school_lookup="school_id")
		return queryset.distinct().order_by(
			"school__name",
			"academic_year__start_date",
			"grade_level",
			"stream",
		)

	def _scope_teacher_queryset(self, queryset):
		return queryset.filter(pk__in=self._teacher_class_ids())


class TeacherListView(HtmxTemplateMixin, AcademicScopedAccessMixin, AcademicModuleReadMixin, ListView):
	model = Teacher
	template_name = "academics/teacher_list.html"
	htmx_template_name = "academics/partials/teacher_results.html"
	context_object_name = "teachers"
	paginate_by = 10
	permission_required = "academics.view_teacher"

	def get_queryset(self):
		queryset = Teacher.objects.select_related("school", "user").prefetch_related(
			"assigned_classes", "assigned_subjects"
		).order_by("user__first_name", "user__last_name")

		q = self.request.GET.get("q", "").strip()
		if q:
			queryset = queryset.filter(
				Q(user__first_name__icontains=q)
				| Q(user__last_name__icontains=q)
				| Q(user__email__icontains=q)
				| Q(employee_number__icontains=q)
				| Q(tsc_number__icontains=q)
				| Q(specialization__icontains=q)
			)

		queryset = self._scope_school_queryset(queryset, school_lookup="school_id")
		return queryset.distinct()

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["q"] = self.request.GET.get("q", "")
		context["page_title"] = "All Teachers"
		return context


class SubjectListView(HtmxTemplateMixin, AcademicScopedAccessMixin, AcademicListContextMixin, AcademicModuleReadMixin, ListView):

	model = Subject
	template_name = "academics/subject_list.html"
	htmx_template_name = "academics/partials/subject_results.html"
	context_object_name = "subjects"
	paginate_by = 12
	page_title = "Subjects"
	create_url_name = "academics:subject-create"
	permission_required = "academics.view_subject"

	def get_queryset(self):
		self.filter_form = SubjectFilterForm(self.request.GET or None, user=self.request.user)
		queryset = Subject.objects.select_related("school").order_by("school__name", "name")

		if self.filter_form.is_valid():
			query = self.filter_form.cleaned_data.get("q")
			school = self.filter_form.cleaned_data.get("school")
			is_active = self.filter_form.cleaned_data.get("is_active")
			is_optional = self.filter_form.cleaned_data.get("is_optional")

			if query:
				queryset = queryset.filter(
					Q(name__icontains=query)
					| Q(code__icontains=query)
					| Q(description__icontains=query)
				)
			if school:
				queryset = queryset.filter(school=school)
			if is_active:
				queryset = queryset.filter(is_active=is_active == "true")
			if is_optional:
				queryset = queryset.filter(is_optional=is_optional == "true")

		queryset = self._scope_school_queryset(queryset, school_lookup="school_id")
		return queryset

	def _scope_teacher_queryset(self, queryset):
		return queryset.filter(pk__in=self._teacher_subject_ids())


class TimetableEntryListView(HtmxTemplateMixin, AcademicScopedAccessMixin, AcademicListContextMixin, AcademicModuleReadMixin, ListView):
	model = TimetableEntry
	template_name = "academics/timetable_list.html"
	htmx_template_name = "academics/partials/timetable_results.html"
	context_object_name = "entries"
	paginate_by = 50
	page_title = "Timetable"
	create_url_name = "academics:timetable-create"
	permission_required = "academics.view_timetableentry"

	def get_queryset(self):
		self.filter_form = TimetableEntryFilterForm(self.request.GET or None, user=self.request.user)
		queryset = TimetableEntry.objects.select_related(
			"school",
			"term",
			"teaching_assignment__class_section__academic_year",
			"teaching_assignment__subject",
			"teaching_assignment__teacher__user",
		)

		if self.filter_form.is_valid():
			query = self.filter_form.cleaned_data.get("q")
			school = self.filter_form.cleaned_data.get("school")
			term = self.filter_form.cleaned_data.get("term")
			class_section = self.filter_form.cleaned_data.get("class_section")
			subject = self.filter_form.cleaned_data.get("subject")
			teacher = self.filter_form.cleaned_data.get("teacher")
			weekday = self.filter_form.cleaned_data.get("weekday")

			if query:
				queryset = queryset.filter(
					Q(period_label__icontains=query)
					| Q(room_name__icontains=query)
					| Q(teaching_assignment__class_section__grade_level__icontains=query)
					| Q(teaching_assignment__class_section__stream__icontains=query)
					| Q(teaching_assignment__subject__name__icontains=query)
					| Q(teaching_assignment__subject__code__icontains=query)
					| Q(teaching_assignment__teacher__user__first_name__icontains=query)
					| Q(teaching_assignment__teacher__user__last_name__icontains=query)
				)
			if school:
				queryset = queryset.filter(school=school)
			if term:
				queryset = queryset.filter(term=term)
			if class_section:
				queryset = queryset.filter(teaching_assignment__class_section=class_section)
			if subject:
				queryset = queryset.filter(teaching_assignment__subject=subject)
			if teacher:
				queryset = queryset.filter(teaching_assignment__teacher=teacher)
			if weekday:
				queryset = queryset.filter(weekday=weekday)

		queryset = self._scope_school_queryset(queryset, school_lookup="school_id")
		return queryset

	def _scope_teacher_queryset(self, queryset):
		return queryset.filter(teaching_assignment__class_section_id__in=self._teacher_class_ids())

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		selected_weekday = None
		if self.filter_form.is_valid():
			selected_weekday = self.filter_form.cleaned_data.get("weekday")

		if selected_weekday:
			weekdays = [
				(weekday_value, weekday_label)
				for weekday_value, weekday_label in TimetableEntry.Weekday.choices
				if str(weekday_value) == str(selected_weekday)
			]
		else:
			weekdays = list(TimetableEntry.Weekday.choices)

		entries = list(context.get("entries", []))
		time_slots = sorted({entry.start_time for entry in entries})

		entry_grid = defaultdict(list)
		for entry in entries:
			entry_grid[(entry.start_time, entry.weekday)].append(entry)

		context["weekdays"] = weekdays
		context["time_slots"] = time_slots
		context["entry_grid"] = dict(entry_grid)

		# Print-friendly metadata
		school = self.request.user.school if self.request.user.school_id else None
		context["school_name"] = school.name if school else ""
		selected_term = self.filter_form.cleaned_data.get("term") if self.filter_form.is_valid() else None
		context["term_name"] = str(selected_term) if selected_term else ""
		return context


class GradeResultListView(HtmxTemplateMixin, AcademicScopedAccessMixin, AcademicListContextMixin, AcademicModuleReadMixin, ListView):
	model = GradeResult
	template_name = "academics/grade_list.html"
	htmx_template_name = "academics/partials/grade_results.html"
	context_object_name = "results"
	paginate_by = 20
	page_title = "Grade results"
	create_url_name = "academics:grade-create"
	permission_required = "academics.view_graderesult"

	def get_queryset(self):
		self.filter_form = GradeResultFilterForm(self.request.GET or None, user=self.request.user)
		queryset = GradeResult.objects.select_related(
			"enrollment__student__user",
			"enrollment__class_section",
			"enrollment__term",
			"enrollment__school",
			"subject",
			"recorded_by",
		)

		if self.filter_form.is_valid():
			query = self.filter_form.cleaned_data.get("q")
			school = self.filter_form.cleaned_data.get("school")
			term = self.filter_form.cleaned_data.get("term")
			class_section = self.filter_form.cleaned_data.get("class_section")
			subject = self.filter_form.cleaned_data.get("subject")
			exam_type = self.filter_form.cleaned_data.get("exam_type")

			if query:
				queryset = queryset.filter(
					Q(enrollment__student__admission_number__icontains=query)
					| Q(enrollment__student__user__first_name__icontains=query)
					| Q(enrollment__student__user__last_name__icontains=query)
					| Q(subject__name__icontains=query)
					| Q(subject__code__icontains=query)
					| Q(grade__icontains=query)
				)
			if school:
				queryset = queryset.filter(enrollment__school=school)
			if term:
				queryset = queryset.filter(enrollment__term=term)
			if class_section:
				queryset = queryset.filter(enrollment__class_section=class_section)
			if subject:
				queryset = queryset.filter(subject=subject)
			if exam_type:
				queryset = queryset.filter(exam_type=exam_type)

		queryset = self._scope_school_queryset(queryset, school_lookup="enrollment__school_id")
		return queryset

	def _scope_teacher_queryset(self, queryset):
		return queryset.filter(enrollment__class_section_id__in=self._teacher_class_ids())


class ClassSectionCreateView(AcademicFormUserKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, CreateView):
	model = ClassSection
	form_class = ClassSectionForm
	template_name = "academics/classsection_form.html"
	htmx_template_name = "academics/partials/classsection_form_modal.html"
	permission_required = "academics.add_classsection"
	form_title = "Create class section"
	submit_label = "Create class section"
	list_url_name = "academics:classsection-list"
	success_message = "Class section created successfully."

	def get_success_url(self):
		return reverse("academics:classsection-list")


class ClassSectionUpdateView(SchoolScopedQuerysetMixin, AcademicFormUserKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, UpdateView):
	# ClassSection has a direct school FK.
	school_lookup = "school_id"
	model = ClassSection
	form_class = ClassSectionForm
	template_name = "academics/classsection_form.html"
	htmx_template_name = "academics/partials/classsection_form_modal.html"
	permission_required = "academics.change_classsection"
	form_title = "Update class section"
	submit_label = "Update class section"
	list_url_name = "academics:classsection-list"
	success_message = "Class section updated successfully."

	def get_success_url(self):
		return reverse("academics:classsection-list")


class SubjectCreateView(AcademicFormUserKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, CreateView):
	model = Subject
	form_class = SubjectForm
	template_name = "academics/subject_form.html"
	htmx_template_name = "academics/partials/subject_form_modal.html"
	permission_required = "academics.add_subject"
	form_title = "Add New Subject"
	submit_label = "Create Subject"
	list_url_name = "academics:subject-list"
	success_message = "Subject created successfully."

	def get_success_url(self):
		return reverse("academics:subject-list")


class SubjectUpdateView(SchoolScopedQuerysetMixin, AcademicFormUserKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, UpdateView):
	# Subject has a direct school FK.
	school_lookup = "school_id"
	model = Subject
	form_class = SubjectForm
	template_name = "academics/subject_form.html"
	htmx_template_name = "academics/partials/subject_form_modal.html"
	permission_required = "academics.change_subject"
	form_title = "Update subject"
	submit_label = "Update subject"
	list_url_name = "academics:subject-list"
	success_message = "Subject updated successfully."

	def get_success_url(self):
		return reverse("academics:subject-list")


class TimetableEntryCreateView(AcademicFormUserKwargsMixin, FilteredFormKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, CreateView):
	model = TimetableEntry
	form_class = TimetableEntryForm
	template_name = "academics/timetable_form.html"
	htmx_template_name = "academics/partials/timetable_form_modal.html"
	permission_required = "academics.add_timetableentry"
	form_title = "Add New Lesson"
	submit_label = "Create Lesson"
	list_url_name = "academics:timetable-list"
	success_message = "Timetable entry created successfully."

	def get_success_url(self):
		return reverse("academics:timetable-list")


class TimetableEntryUpdateView(SchoolScopedQuerysetMixin, AcademicFormUserKwargsMixin, FilteredFormKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, UpdateView):
	# TimetableEntry has a direct school FK.
	school_lookup = "school_id"
	model = TimetableEntry
	form_class = TimetableEntryForm
	template_name = "academics/timetable_form.html"
	htmx_template_name = "academics/partials/timetable_form_modal.html"
	permission_required = "academics.change_timetableentry"
	form_title = "Update timetable entry"
	submit_label = "Update timetable entry"
	list_url_name = "academics:timetable-list"
	success_message = "Timetable entry updated successfully."

	def get_success_url(self):
		return reverse("academics:timetable-list")


class GradeResultCreateView(AcademicFormUserKwargsMixin, FilteredFormKwargsMixin, AcademicScopedAccessMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicGradeWriteMixin, CreateView):
	model = GradeResult
	form_class = GradeResultForm
	template_name = "academics/grade_form.html"
	htmx_template_name = "academics/partials/grade_form_modal.html"
	permission_required = "academics.add_graderesult"
	form_title = "Record grade result"
	submit_label = "Save grade result"
	list_url_name = "academics:grade-list"
	success_message = "Grade result saved successfully."

	def _resolve_post_enrollment_and_subject(self):
		enrollment_id = self.request.POST.get("enrollment")
		subject_id = self.request.POST.get("subject")
		if not enrollment_id or not subject_id:
			return None, None
		enrollment = Enrollment.objects.select_related("class_section", "school").filter(pk=enrollment_id).first()
		subject = Subject.objects.select_related("school").filter(pk=subject_id).first()
		return enrollment, subject

	def post(self, request, *args, **kwargs):
		enrollment, subject = self._resolve_post_enrollment_and_subject()
		if request.user.role == User.Role.TEACHER and enrollment and subject:
			self._validate_grade_write_permission(enrollment=enrollment, subject=subject)
		return super().post(request, *args, **kwargs)

	def form_valid(self, form):
		self._validate_grade_write_permission(
			enrollment=form.instance.enrollment,
			subject=form.instance.subject,
		)
		if not form.instance.exam_type:
			form.instance.exam_type = GradeResult.ExamType.END_TERM
		form.instance.recorded_by = self.request.user
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("academics:grade-list")


class GradeResultUpdateView(SchoolScopedQuerysetMixin, AcademicFormUserKwargsMixin, FilteredFormKwargsMixin, AcademicScopedAccessMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicGradeWriteMixin, UpdateView):
	# GradeResult -> enrollment (students.Enrollment) -> school
	school_lookup = "enrollment__school_id"
	model = GradeResult
	form_class = GradeResultForm
	template_name = "academics/grade_form.html"
	htmx_template_name = "academics/partials/grade_form_modal.html"
	permission_required = "academics.change_graderesult"
	form_title = "Update grade result"
	submit_label = "Update grade result"
	list_url_name = "academics:grade-list"
	success_message = "Grade result updated successfully."

	def _resolve_post_enrollment_and_subject(self):
		enrollment_id = self.request.POST.get("enrollment")
		subject_id = self.request.POST.get("subject")
		if not enrollment_id or not subject_id:
			return None, None
		enrollment = Enrollment.objects.select_related("class_section", "school").filter(pk=enrollment_id).first()
		subject = Subject.objects.select_related("school").filter(pk=subject_id).first()
		return enrollment, subject

	def post(self, request, *args, **kwargs):
		enrollment, subject = self._resolve_post_enrollment_and_subject()
		if request.user.role == User.Role.TEACHER and enrollment and subject:
			self._validate_grade_write_permission(enrollment=enrollment, subject=subject)
		return super().post(request, *args, **kwargs)

	def form_valid(self, form):
		self._validate_grade_write_permission(
			enrollment=form.instance.enrollment,
			subject=form.instance.subject,
		)
		if not form.instance.exam_type:
			form.instance.exam_type = GradeResult.ExamType.END_TERM
		form.instance.recorded_by = self.request.user
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("academics:grade-list")


class TeacherDetailView(AcademicScopedAccessMixin, AcademicModuleReadMixin, DetailView):
	model = Teacher
	template_name = "academics/teacher_detail.html"
	context_object_name = "teacher"
	permission_required = "academics.view_teacher"

	def get_queryset(self):
		queryset = Teacher.objects.select_related("school", "user").prefetch_related(
			"assigned_classes", "assigned_subjects"
		)
		queryset = self._scope_school_queryset(queryset, school_lookup="school_id")
		return queryset

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		teacher = self.object
		classes = teacher.get_assigned_classes()
		context["classes"] = classes

		from students.models import Student
		context["students"] = Student.objects.filter(
			enrollments__class_section__in=classes,
			enrollments__status="active"
		).distinct().select_related("user").order_by("user__first_name", "user__last_name")

		return context


class TeacherCreateView(AcademicFormUserKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, CreateView):
	model = Teacher
	form_class = TeacherForm
	template_name = "academics/teacher_form.html"
	htmx_template_name = "academics/partials/teacher_form_modal.html"
	permission_required = "academics.add_teacher"
	form_title = "Create teacher"
	submit_label = "Create teacher"
	list_url_name = "academics:teacher-list"
	success_message = "Teacher created successfully."

	def get_success_url(self):
		return reverse("academics:teacher-detail", kwargs={"pk": self.object.pk})


class TeacherUpdateView(SchoolScopedQuerysetMixin, AcademicFormUserKwargsMixin, HtmxTemplateMixin, AcademicFormContextMixin, SuccessMessageFormMixin, AcademicModuleAdminWriteMixin, UpdateView):
	# Teacher has a direct school FK.
	school_lookup = "school_id"
	model = Teacher
	form_class = TeacherForm
	template_name = "academics/teacher_form.html"
	htmx_template_name = "academics/partials/teacher_form_modal.html"
	permission_required = "academics.change_teacher"
	form_title = "Update teacher"
	submit_label = "Update teacher"
	list_url_name = "academics:teacher-list"
	success_message = "Teacher updated successfully."

	def get_success_url(self):
		return reverse("academics:teacher-detail", kwargs={"pk": self.object.pk})

