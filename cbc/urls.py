from django.urls import path

from cbc.views import (
    CBCBulkGenerateStubView,
    CBCReportCreateView,
    CBCReportDetailView,
    CBCReportListView,
    CBCReportPDFView,
    CBCReportRefreshAttendanceView,
    CBCReportUpdateView,
    StrandCreateView,
    StrandDeleteView,
    StrandListView,
    StrandUpdateView,
    StudentCBCHistoryView,
    SubStrandCreateView,
    SubStrandDeleteView,
    SubStrandUpdateView,
)


app_name = "cbc"

urlpatterns = [
    # Reports
    path("reports/", CBCReportListView.as_view(), name="report-list"),
    path("reports/new/", CBCReportCreateView.as_view(), name="report-create"),
    path("reports/<int:pk>/", CBCReportDetailView.as_view(), name="report-detail"),
    path("reports/<int:pk>/edit/", CBCReportUpdateView.as_view(), name="report-edit"),
    path("reports/<int:pk>/refresh-attendance/", CBCReportRefreshAttendanceView.as_view(), name="report-refresh-attendance"),
    path("reports/<int:pk>/pdf/", CBCReportPDFView.as_view(), name="report-pdf"),
    path("reports/bulk/", CBCBulkGenerateStubView.as_view(), name="report-bulk"),
    # Per-student history
    path(
        "students/<int:student_pk>/cbc/",
        StudentCBCHistoryView.as_view(),
        name="student-history",
    ),
    path("students/<int:student_pk>/history/", StudentCBCHistoryView.as_view()),
    # Strand catalog
    path("strands/", StrandListView.as_view(), name="strand-list"),
    path("strands/new/", StrandCreateView.as_view(), name="strand-create"),
    path("strands/<int:pk>/edit/", StrandUpdateView.as_view(), name="strand-edit"),
    path(
        "strands/<int:pk>/delete/",
        StrandDeleteView.as_view(),
        name="strand-delete",
    ),
    path(
        "strands/<int:strand_pk>/sub-strands/new/",
        SubStrandCreateView.as_view(),
        name="sub-strand-create",
    ),
    path(
        "sub-strands/<int:pk>/edit/",
        SubStrandUpdateView.as_view(),
        name="sub-strand-edit",
    ),
    path(
        "sub-strands/<int:pk>/delete/",
        SubStrandDeleteView.as_view(),
        name="sub-strand-delete",
    ),
]
