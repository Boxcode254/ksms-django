from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "audience", "is_active", "author", "created_at")
    list_filter = ("audience", "is_active", "school")
    search_fields = ("title", "body", "author__username", "author__first_name", "author__last_name")
    list_select_related = ("school", "author")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
