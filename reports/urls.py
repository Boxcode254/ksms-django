from django.urls import path

from .views import (
    AcademicSummaryCSVView,
    AcademicSummaryPDFView,
    AcademicSummaryView,
    AttendanceReportCSVView,
    AttendanceReportPDFView,
    AttendanceReportView,
    FeeReportCSVView,
    FeeReportPDFView,
    FeeReportView,
    StudentRegisterCSVView,
    StudentRegisterPDFView,
    StudentRegisterView,
    StudentReportCardView,
)

app_name = 'reports'

urlpatterns = [
    path('attendance/', AttendanceReportView.as_view(), name='attendance'),
    path('attendance/csv/', AttendanceReportCSVView.as_view(), name='attendance-csv'),
    path('attendance/pdf/', AttendanceReportPDFView.as_view(), name='attendance-pdf'),
    path('fees/', FeeReportView.as_view(), name='fees'),
    path('fees/csv/', FeeReportCSVView.as_view(), name='fees-csv'),
    path('fees/pdf/', FeeReportPDFView.as_view(), name='fees-pdf'),
    path('students/', StudentRegisterView.as_view(), name='students'),
    path('students/csv/', StudentRegisterCSVView.as_view(), name='students-csv'),
    path('students/pdf/', StudentRegisterPDFView.as_view(), name='students-pdf'),
    path('academics/', AcademicSummaryView.as_view(), name='academics'),
    path('academics/csv/', AcademicSummaryCSVView.as_view(), name='academics-csv'),
    path('academics/pdf/', AcademicSummaryPDFView.as_view(), name='academics-pdf'),
    path('students/<int:pk>/report-card/', StudentReportCardView.as_view(), name='report-card'),
]
