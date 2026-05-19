from django.urls import path

from .views import (
    AnnouncementCreateView,
    AnnouncementDeleteView,
    AnnouncementDetailView,
    AnnouncementListView,
    AnnouncementUpdateView,
)

app_name = "communication"

urlpatterns = [
    path("announcements/", AnnouncementListView.as_view(), name="announcement-list"),
    path("announcements/create/", AnnouncementCreateView.as_view(), name="announcement-create"),
    path("announcements/<int:pk>/", AnnouncementDetailView.as_view(), name="announcement-detail"),
    path("announcements/<int:pk>/edit/", AnnouncementUpdateView.as_view(), name="announcement-update"),
    path("announcements/<int:pk>/delete/", AnnouncementDeleteView.as_view(), name="announcement-delete"),
]
