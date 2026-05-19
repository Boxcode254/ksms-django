from django.urls import path

from .views import (
	DailyAttendanceCreateView,
	DailyAttendanceUpdateView,
	PeriodAttendanceCreateView,
	PeriodAttendanceListView,
	PeriodAttendanceUpdateView,
	TakeAttendanceView,
)

app_name = "attendance"

urlpatterns = [
	path("attendance/daily/", TakeAttendanceView.as_view(), name="daily-list"),
	path("attendance/daily/create/", DailyAttendanceCreateView.as_view(), name="daily-create"),
	path("attendance/daily/<int:pk>/edit/", DailyAttendanceUpdateView.as_view(), name="daily-update"),
	path("attendance/period/", PeriodAttendanceListView.as_view(), name="period-list"),
	path("attendance/period/create/", PeriodAttendanceCreateView.as_view(), name="period-create"),
	path("attendance/period/<int:pk>/edit/", PeriodAttendanceUpdateView.as_view(), name="period-update"),
]