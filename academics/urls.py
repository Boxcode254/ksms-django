from django.urls import path

from .views import (
	ClassSectionCreateView,
	ClassSectionListView,
	ClassSectionUpdateView,
	GradeResultCreateView,
	GradeResultListView,
	GradeResultUpdateView,
	SubjectCreateView,
	SubjectListView,
	SubjectUpdateView,
	TeacherCreateView,
	TeacherDetailView,
	TeacherListView,
	TeacherUpdateView,
	TimetableEntryCreateView,

	TimetableEntryListView,
	TimetableEntryUpdateView,
)

app_name = "academics"

urlpatterns = [
	path("academics/classes/", ClassSectionListView.as_view(), name="classsection-list"),
	path("academics/classes/create/", ClassSectionCreateView.as_view(), name="classsection-create"),
	path("academics/classes/<int:pk>/edit/", ClassSectionUpdateView.as_view(), name="classsection-update"),
	path("academics/subjects/", SubjectListView.as_view(), name="subject-list"),
	path("academics/subjects/create/", SubjectCreateView.as_view(), name="subject-create"),
	path("academics/subjects/<int:pk>/edit/", SubjectUpdateView.as_view(), name="subject-update"),
	path("academics/timetable/", TimetableEntryListView.as_view(), name="timetable-list"),
	path("academics/timetable/create/", TimetableEntryCreateView.as_view(), name="timetable-create"),
	path("academics/timetable/<int:pk>/edit/", TimetableEntryUpdateView.as_view(), name="timetable-update"),
	path("academics/teachers/", TeacherListView.as_view(), name="teacher-list"),
	path("academics/teachers/create/", TeacherCreateView.as_view(), name="teacher-create"),
	path("academics/teachers/<int:pk>/", TeacherDetailView.as_view(), name="teacher-detail"),
	path("academics/teachers/<int:pk>/edit/", TeacherUpdateView.as_view(), name="teacher-update"),
	path("academics/grades/", GradeResultListView.as_view(), name="grade-list"),
	path("academics/grades/create/", GradeResultCreateView.as_view(), name="grade-create"),
	path("academics/grades/<int:pk>/edit/", GradeResultUpdateView.as_view(), name="grade-update"),
]