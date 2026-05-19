from django.contrib import admin

from .models import (
	AcademicYear,
	ClassSection,
	ExamWeightPolicy,
	GradeResult,
	KNECGradeBand,
	Subject,
	Teacher,
	TeachingAssignment,
	Term,
	TimetableEntry,
)


@admin.action(description="Mark selected academic years as current")
def mark_years_current(modeladmin, request, queryset):
	schools = set(queryset.values_list("school_id", flat=True))
	for school_id in schools:
		school_years = queryset.filter(school_id=school_id)
		if school_years.exists():
			AcademicYear.objects.filter(school_id=school_id).update(is_current=False)
			school_years.update(is_current=True)


@admin.action(description="Mark selected terms as current")
def mark_terms_current(modeladmin, request, queryset):
	schools = set(queryset.values_list("school_id", flat=True))
	for school_id in schools:
		school_terms = queryset.filter(school_id=school_id)
		if school_terms.exists():
			Term.objects.filter(school_id=school_id).update(is_current=False)
			school_terms.update(is_current=True)


@admin.action(description="Activate selected subjects")
def activate_subjects(modeladmin, request, queryset):
	queryset.update(is_active=True)


@admin.action(description="Deactivate selected subjects")
def deactivate_subjects(modeladmin, request, queryset):
	queryset.update(is_active=False)


@admin.action(description="Activate selected teacher user accounts")
def activate_teacher_users(modeladmin, request, queryset):
	for teacher in queryset.select_related("user"):
		if not teacher.user.is_active:
			teacher.user.is_active = True
			teacher.user.save(update_fields=["is_active"])


class TeachingAssignmentInline(admin.TabularInline):
	model = TeachingAssignment
	extra = 0
	autocomplete_fields = ("subject", "teacher")


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
	list_display = ("name", "school", "start_date", "end_date", "is_current")
	list_filter = ("school", "is_current")
	search_fields = ("name", "school__name", "school__code")
	autocomplete_fields = ("school",)
	readonly_fields = ("created_at", "updated_at")
	ordering = ("school", "-start_date")
	actions = (mark_years_current,)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
	list_display = ("name", "academic_year", "school", "start_date", "end_date", "is_current")
	list_filter = ("school", "academic_year", "is_current")
	search_fields = ("academic_year__name", "school__name")
	autocomplete_fields = ("school", "academic_year")
	readonly_fields = ("created_at", "updated_at")
	ordering = ("school", "academic_year", "start_date")
	actions = (mark_terms_current,)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
	list_display = ("teacher_name", "school", "employee_number", "tsc_number", "hire_date", "user_active")
	list_filter = ("school", "hire_date")
	search_fields = (
		"employee_number",
		"tsc_number",
		"user__username",
		"user__first_name",
		"user__last_name",
		"user__email",
	)
	autocomplete_fields = ("school", "user")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("school", "user")
	ordering = ("school", "employee_number")
	actions = (activate_teacher_users,)

	@admin.display(ordering="user__first_name", description="Teacher")
	def teacher_name(self, obj):
		return obj.user.get_full_name() or obj.user.username

	@admin.display(boolean=True, description="User active")
	def user_active(self, obj):
		return obj.user.is_active


@admin.register(ClassSection)
class ClassSectionAdmin(admin.ModelAdmin):
	list_display = ("section_name", "school", "academic_year", "homeroom_teacher", "capacity", "room_name")
	list_filter = ("school", "academic_year", "grade_level")
	search_fields = ("grade_level", "stream", "room_name", "school__name", "homeroom_teacher__user__first_name", "homeroom_teacher__user__last_name")
	autocomplete_fields = ("school", "academic_year", "homeroom_teacher")
	readonly_fields = ("created_at", "updated_at")
	inlines = (TeachingAssignmentInline,)
	list_select_related = ("school", "academic_year", "homeroom_teacher__user")
	ordering = ("school", "academic_year", "grade_level", "stream")

	@admin.display(ordering="grade_level", description="Class section")
	def section_name(self, obj):
		return obj.display_name


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
	list_display = ("name", "code", "school", "is_optional", "is_active")
	list_filter = ("school", "is_optional", "is_active")
	search_fields = ("name", "code", "school__name")
	autocomplete_fields = ("school",)
	readonly_fields = ("created_at", "updated_at")
	ordering = ("school", "name")
	actions = (activate_subjects, deactivate_subjects)


@admin.register(TeachingAssignment)
class TeachingAssignmentAdmin(admin.ModelAdmin):
	list_display = ("class_section", "subject", "teacher", "school")
	list_filter = ("school", "class_section__academic_year")
	search_fields = (
		"class_section__grade_level",
		"class_section__stream",
		"subject__name",
		"subject__code",
		"teacher__user__first_name",
		"teacher__user__last_name",
	)
	autocomplete_fields = ("school", "class_section", "subject", "teacher")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("school", "class_section", "subject", "teacher__user")
	ordering = ("school", "class_section", "subject")


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
	list_display = (
		"weekday_display",
		"period_label",
		"start_time",
		"end_time",
		"class_section",
		"subject",
		"teacher",
		"room_name",
		"school",
	)
	list_filter = ("school", "term", "weekday", "teaching_assignment__class_section__academic_year")
	search_fields = (
		"period_label",
		"room_name",
		"teaching_assignment__class_section__grade_level",
		"teaching_assignment__class_section__stream",
		"teaching_assignment__subject__name",
		"teaching_assignment__subject__code",
		"teaching_assignment__teacher__user__first_name",
		"teaching_assignment__teacher__user__last_name",
	)
	autocomplete_fields = ("school", "term", "teaching_assignment")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = (
		"school",
		"term",
		"teaching_assignment__class_section",
		"teaching_assignment__subject",
		"teaching_assignment__teacher__user",
	)
	ordering = ("school", "term", "weekday", "start_time")

	@admin.display(ordering="weekday", description="Weekday")
	def weekday_display(self, obj):
		return obj.get_weekday_display()

	@admin.display(ordering="teaching_assignment__class_section", description="Class section")
	def class_section(self, obj):
		return obj.class_section.display_name

	@admin.display(ordering="teaching_assignment__subject", description="Subject")
	def subject(self, obj):
		return obj.subject.name

	@admin.display(ordering="teaching_assignment__teacher__user__first_name", description="Teacher")
	def teacher(self, obj):
		return obj.teacher.user.get_full_name() or obj.teacher.user.username


@admin.register(GradeResult)
class GradeResultAdmin(admin.ModelAdmin):
	list_display = ("student_name", "class_section", "subject", "exam_type", "score", "grade", "recorded_by", "created_at")
	list_filter = ("subject", "exam_type", "enrollment__school", "enrollment__term", "grade")
	search_fields = (
		"enrollment__student__admission_number",
		"enrollment__student__user__first_name",
		"enrollment__student__user__last_name",
		"subject__name",
		"subject__code",
	)
	autocomplete_fields = ("enrollment", "subject", "recorded_by")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = (
		"enrollment__student__user",
		"enrollment__class_section",
		"subject",
		"recorded_by",
	)
	ordering = ("-created_at",)

	@admin.display(ordering="enrollment__student__admission_number", description="Student")
	def student_name(self, obj):
		return str(obj.enrollment.student)

	@admin.display(ordering="enrollment__class_section", description="Class section")
	def class_section(self, obj):
		return obj.enrollment.class_section.display_name


@admin.register(ExamWeightPolicy)
class ExamWeightPolicyAdmin(admin.ModelAdmin):
	list_display = ("school", "cat_weight", "mid_term_weight", "end_term_weight", "mock_weight", "updated_at")
	search_fields = ("school__name", "school__code")
	autocomplete_fields = ("school",)
	readonly_fields = ("created_at", "updated_at")


@admin.register(KNECGradeBand)
class KNECGradeBandAdmin(admin.ModelAdmin):
	list_display = ("school", "grade", "points", "min_score", "max_score", "order")
	list_filter = ("school",)
	search_fields = ("school__name", "school__code", "grade")
	autocomplete_fields = ("school",)
	readonly_fields = ("created_at", "updated_at")
	ordering = ("school", "order", "-max_score")
