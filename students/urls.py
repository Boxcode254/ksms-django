from django.urls import path

from .views import (
    DeletedGuardianListView,
    DeletedStudentListView,
    EnrollmentCreateView,
    EnrollmentUpdateView,
    GuardianCreateView,
    GuardianDetailView,
    GuardianListView,
    GuardianUpdateView,
    RestoreGuardianView,
    RestoreStudentView,
    StudentCreateView,
    StudentDetailView,
    StudentGuardianRelationshipCreateView,
    StudentGuardianRelationshipDeleteView,
    StudentGuardianRelationshipUpdateView,
    StudentListView,
    StudentUpdateView,
)

app_name = "students"

urlpatterns = [
    path("students/", StudentListView.as_view(), name="student-list"),
    path("students/create/", StudentCreateView.as_view(), name="student-create"),
    path("students/<int:pk>/", StudentDetailView.as_view(), name="student-detail"),
    path("students/<int:pk>/edit/", StudentUpdateView.as_view(), name="student-update"),
    path(
        "students/<int:student_pk>/relationships/add/",
        StudentGuardianRelationshipCreateView.as_view(),
        name="relationship-create",
    ),
    path(
        "relationships/<int:pk>/edit/",
        StudentGuardianRelationshipUpdateView.as_view(),
        name="relationship-update",
    ),
    path(
        "relationships/<int:pk>/delete/",
        StudentGuardianRelationshipDeleteView.as_view(),
        name="relationship-delete",
    ),
    path(
        "students/<int:student_pk>/enrollments/add/",
        EnrollmentCreateView.as_view(),
        name="enrollment-create",
    ),
    path("enrollments/<int:pk>/edit/", EnrollmentUpdateView.as_view(), name="enrollment-update"),
    path("guardians/", GuardianListView.as_view(), name="guardian-list"),
    path("guardians/create/", GuardianCreateView.as_view(), name="guardian-create"),
    path("guardians/<int:pk>/", GuardianDetailView.as_view(), name="guardian-detail"),
    path("guardians/<int:pk>/edit/", GuardianUpdateView.as_view(), name="guardian-update"),
    path("students/deleted/", DeletedStudentListView.as_view(), name="student-deleted-list"),
    path("guardians/deleted/", DeletedGuardianListView.as_view(), name="guardian-deleted-list"),
    path("students/<int:pk>/restore/", RestoreStudentView.as_view(), name="student-restore"),
    path("guardians/<int:pk>/restore/", RestoreGuardianView.as_view(), name="guardian-restore"),
]