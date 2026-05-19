from django.contrib import admin

from core.encryption import fingerprint_value

from .models import Enrollment, Guardian, Student, StudentGuardianRelationship


@admin.action(description="Mark selected students as active")
def mark_students_active(modeladmin, request, queryset):
	queryset.update(status=Student.Status.ACTIVE)


@admin.action(description="Mark selected students as suspended")
def mark_students_suspended(modeladmin, request, queryset):
	queryset.update(status=Student.Status.SUSPENDED)


@admin.action(description="Mark selected students as graduated")
def mark_students_graduated(modeladmin, request, queryset):
	queryset.update(status=Student.Status.GRADUATED)


@admin.action(description="Activate selected guardian user accounts")
def activate_guardian_users(modeladmin, request, queryset):
	for guardian in queryset.select_related("user"):
		if not guardian.user.is_active:
			guardian.user.is_active = True
			guardian.user.save(update_fields=["is_active"])


@admin.action(description="Deactivate selected guardian user accounts")
def deactivate_guardian_users(modeladmin, request, queryset):
	for guardian in queryset.select_related("user"):
		if guardian.user.is_active:
			guardian.user.is_active = False
			guardian.user.save(update_fields=["is_active"])


@admin.action(description="Mark selected enrollments as active")
def mark_enrollments_active(modeladmin, request, queryset):
	queryset.update(status=Enrollment.Status.ACTIVE)


@admin.action(description="Mark selected enrollments as completed")
def mark_enrollments_completed(modeladmin, request, queryset):
	queryset.update(status=Enrollment.Status.COMPLETED)


@admin.action(description="Mark selected enrollments as transferred")
def mark_enrollments_transferred(modeladmin, request, queryset):
	queryset.update(status=Enrollment.Status.TRANSFERRED)


class StudentGuardianInline(admin.TabularInline):
	model = StudentGuardianRelationship
	fk_name = "student"
	extra = 0
	autocomplete_fields = ("guardian",)


class GuardianStudentInline(admin.TabularInline):
	model = StudentGuardianRelationship
	fk_name = "guardian"
	extra = 0
	autocomplete_fields = ("student",)


class EnrollmentInline(admin.TabularInline):
	model = Enrollment
	extra = 0
	autocomplete_fields = ("school", "academic_year", "term", "class_section")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
	list_display = ("admission_number", "student_name", "school", "status", "admission_date", "current_class_section")
	list_filter = ("school", "status", "gender")
	search_fields = (
		"admission_number",
		"user__username",
		"user__first_name",
		"user__last_name",
		"user__email",
	)
	autocomplete_fields = ("school", "user")
	readonly_fields = ("created_at", "updated_at")
	inlines = (StudentGuardianInline, EnrollmentInline)
	list_select_related = ("school", "user")
	ordering = ("school", "admission_number")
	actions = (mark_students_active, mark_students_suspended, mark_students_graduated)

	@admin.display(ordering="user__first_name", description="Student")
	def student_name(self, obj):
		return obj.user.get_full_name() or obj.user.username

	@admin.display(description="Current class")
	def current_class_section(self, obj):
		current = obj.enrollments.filter(status=Enrollment.Status.ACTIVE).select_related("class_section").first()
		return current.class_section.display_name if current else "-"


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
	list_display = ("guardian_name", "school", "occupation", "user_email", "user_phone")
	list_filter = ("school",)
	search_fields = (
		"user__username",
		"user__first_name",
		"user__last_name",
		"user__email",
	)
	autocomplete_fields = ("school", "user")
	readonly_fields = ("created_at", "updated_at")
	inlines = (GuardianStudentInline,)
	list_select_related = ("school", "user")
	ordering = ("school", "user__first_name", "user__last_name")
	actions = (activate_guardian_users, deactivate_guardian_users)

	@admin.display(ordering="user__first_name", description="Guardian")
	def guardian_name(self, obj):
		return obj.user.get_full_name() or obj.user.username

	@admin.display(ordering="user__email", description="Email")
	def user_email(self, obj):
		return obj.user.email

	@admin.display(ordering="user__phone", description="Phone")
	def user_phone(self, obj):
		return obj.user.phone

	def get_search_results(self, request, queryset, search_term):
		queryset, use_distinct = super().get_search_results(request, queryset, search_term)
		national_id_fingerprint = fingerprint_value(search_term)
		if national_id_fingerprint:
			queryset = queryset | self.model.objects.filter(national_id_fingerprint=national_id_fingerprint)
			queryset = queryset.distinct()
			use_distinct = True
		return queryset, use_distinct


@admin.register(StudentGuardianRelationship)
class StudentGuardianRelationshipAdmin(admin.ModelAdmin):
	list_display = ("student", "guardian", "relationship", "is_primary_contact", "is_emergency_contact", "is_fee_payer")
	list_filter = ("relationship", "is_primary_contact", "is_emergency_contact", "is_fee_payer", "student__school")
	search_fields = (
		"student__admission_number",
		"student__user__first_name",
		"student__user__last_name",
		"guardian__user__first_name",
		"guardian__user__last_name",
	)
	autocomplete_fields = ("student", "guardian")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("student__user", "guardian__user")
	ordering = ("student", "guardian")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
	list_display = ("student", "school", "class_section", "term", "status", "roll_number", "start_date")
	list_filter = ("school", "academic_year", "term", "status", "class_section")
	search_fields = (
		"student__admission_number",
		"student__user__first_name",
		"student__user__last_name",
		"class_section__grade_level",
		"class_section__stream",
	)
	autocomplete_fields = ("school", "student", "academic_year", "term", "class_section")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("school", "student__user", "academic_year", "term", "class_section")
	ordering = ("school", "-start_date")
	date_hierarchy = "start_date"
	actions = (mark_enrollments_active, mark_enrollments_completed, mark_enrollments_transferred)
