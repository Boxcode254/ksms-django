from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, School, User


@admin.action(description="Mark selected schools as active")
def mark_schools_active(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description="Mark selected schools as inactive")
def mark_schools_inactive(modeladmin, request, queryset):
    queryset.update(is_active=False)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "county", "phone", "email", "has_stamp", "is_active", "updated_at")
    list_filter = ("is_active", "county")
    search_fields = ("name", "code", "registration_number", "email", "phone")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)
    actions = (mark_schools_active, mark_schools_inactive)

    @admin.display(boolean=True, description="Stamp")
    def has_stamp(self, obj):
        return bool(obj.stamp_image)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'school', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ("username", "first_name", "last_name", "email", "phone")
    ordering = ("username",)
    fieldsets = UserAdmin.fieldsets + (
        ('KSMS', {'fields': ('role', 'school', 'phone', 'avatar')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('KSMS', {'fields': ('email', 'role', 'school', 'phone', 'avatar')}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'actor', 'object_repr', 'ip_address')
    list_filter = ('action', 'content_type', 'created_at')
    search_fields = ('actor__username', 'actor__email', 'object_repr', 'ip_address')
    date_hierarchy = "created_at"
    readonly_fields = (
        'actor',
        'action',
        'content_type',
        'object_id',
        'object_repr',
        'ip_address',
        'user_agent',
        'metadata',
        'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
