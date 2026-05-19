from django.contrib import admin

from .models import AttendanceStatus, DailyAttendance, PeriodAttendance


def _update_attendance_status(queryset, status):
	queryset.update(status=status)


@admin.action(description="Mark selected attendance records as present")
def mark_present(modeladmin, request, queryset):
	_update_attendance_status(queryset, AttendanceStatus.PRESENT)


@admin.action(description="Mark selected attendance records as absent")
def mark_absent(modeladmin, request, queryset):
	_update_attendance_status(queryset, AttendanceStatus.ABSENT)


@admin.action(description="Mark selected attendance records as excused")
def mark_excused(modeladmin, request, queryset):
	_update_attendance_status(queryset, AttendanceStatus.EXCUSED)


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(admin.ModelAdmin):
	list_display = ("attendance_date", "student", "class_section", "status", "recorded_by")
	list_filter = ("status", "attendance_date", "enrollment__school", "enrollment__term")
	search_fields = (
		"enrollment__student__admission_number",
		"enrollment__student__user__first_name",
		"enrollment__student__user__last_name",
		"enrollment__class_section__grade_level",
		"enrollment__class_section__stream",
	)
	autocomplete_fields = ("enrollment", "recorded_by")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("enrollment__student__user", "enrollment__class_section", "recorded_by")
	ordering = ("-attendance_date",)
	date_hierarchy = "attendance_date"
	actions = (mark_present, mark_absent, mark_excused)


@admin.register(PeriodAttendance)
class PeriodAttendanceAdmin(admin.ModelAdmin):
	list_display = ("attendance_date", "period_number", "student", "class_section", "subject", "status", "recorded_by")
	list_filter = ("status", "attendance_date", "period_number", "subject", "enrollment__school")
	search_fields = (
		"enrollment__student__admission_number",
		"enrollment__student__user__first_name",
		"enrollment__student__user__last_name",
		"subject__name",
		"subject__code",
	)
	autocomplete_fields = ("enrollment", "subject", "recorded_by")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("enrollment__student__user", "enrollment__class_section", "subject", "recorded_by")
	ordering = ("-attendance_date", "period_number")
	date_hierarchy = "attendance_date"
	actions = (mark_present, mark_absent, mark_excused)
