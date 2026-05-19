import datetime

from django.test import TestCase
from django.urls import reverse

from academics.models import (
	AcademicYear,
	ClassSection,
	GradeResult,
	Subject,
	Teacher,
	TeachingAssignment,
	Term,
	TimetableEntry,
)
from core.models import School, User
from core.signals import sync_role_group_membership
from students.models import Enrollment, Student


class AcademicsModuleTestCase(TestCase):
	"""Shared fixtures for all Module 3 tests."""

	@classmethod
	def setUpTestData(cls):
		cls.school = School.objects.create(
			name="KSMS Academics School",
			code="ACASCH",
			slug="ksms-academics-school",
			email="academics@testschool.example.com",
			phone="+254700000099",
			county="Nairobi",
		)
		cls.academic_year = AcademicYear.objects.create(
			school=cls.school,
			name="2026",
			start_date=datetime.date(2026, 1, 5),
			end_date=datetime.date(2026, 11, 20),
			is_current=True,
		)
		cls.term = Term.objects.create(
			school=cls.school,
			academic_year=cls.academic_year,
			name=Term.Name.TERM_1,
			start_date=datetime.date(2026, 1, 5),
			end_date=datetime.date(2026, 4, 10),
			is_current=True,
		)

		cls.admin_user = User.objects.create_user(
			username="admin.academics",
			email="admin.academics@example.com",
			password="TestPass1234",
			role=User.Role.SCHOOL_ADMIN,
			school=cls.school,
			first_name="Academics",
			last_name="Admin",
		)
		sync_role_group_membership(cls.admin_user)

		cls.teacher_user = User.objects.create_user(
			username="teacher.academics",
			email="teacher.academics@example.com",
			password="TestPass1234",
			role=User.Role.TEACHER,
			school=cls.school,
			first_name="Academics",
			last_name="Teacher",
		)
		sync_role_group_membership(cls.teacher_user)

		cls.student_user = User.objects.create_user(
			username="student.academics",
			email="student.academics@example.com",
			password="TestPass1234",
			role=User.Role.STUDENT,
		)
		sync_role_group_membership(cls.student_user)

		cls.parent_user = User.objects.create_user(
			username="parent.academics",
			email="parent.academics@example.com",
			password="TestPass1234",
			role=User.Role.PARENT,
		)
		sync_role_group_membership(cls.parent_user)

		cls.teacher_profile = Teacher.objects.create(
			school=cls.school,
			user=cls.teacher_user,
			employee_number="TCHR-ACA-01",
			hire_date=datetime.date(2026, 1, 7),
		)

		cls.section = ClassSection.objects.create(
			school=cls.school,
			academic_year=cls.academic_year,
			grade_level="Form 2",
			stream="B",
			capacity=40,
		)
		cls.subject = Subject.objects.create(
			school=cls.school,
			name="Biology",
			code="BIO",
			is_active=True,
		)
		cls.assignment = TeachingAssignment.objects.create(
			school=cls.school,
			class_section=cls.section,
			subject=cls.subject,
			teacher=cls.teacher_profile,
		)
		cls.timetable_entry = TimetableEntry.objects.create(
			school=cls.school,
			term=cls.term,
			teaching_assignment=cls.assignment,
			weekday=TimetableEntry.Weekday.MONDAY,
			start_time=datetime.time(8, 0),
			end_time=datetime.time(9, 0),
			period_label="P1",
		)

		cls.student = Student.objects.create(
			school=cls.school,
			user=cls.student_user,
			admission_number="ACA-001",
			admission_date=datetime.date(2026, 1, 9),
		)
		cls.enrollment = Enrollment.objects.create(
			school=cls.school,
			student=cls.student,
			academic_year=cls.academic_year,
			term=cls.term,
			class_section=cls.section,
			status=Enrollment.Status.ACTIVE,
			start_date=cls.term.start_date,
			roll_number=1,
		)
		cls.grade_result = GradeResult.objects.create(
			enrollment=cls.enrollment,
			subject=cls.subject,
			score="85.50",
			grade="A",
			recorded_by=cls.teacher_user,
		)

	def login(self, user):
		self.client.force_login(user)


# ---------------------------------------------------------------------------
# Permission / access tests
# ---------------------------------------------------------------------------

class AcademicsPermissionTests(AcademicsModuleTestCase):

	def test_classsection_list_requires_login(self):
		response = self.client.get(reverse("academics:classsection-list"))
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("account_login"), response.url)

	def test_subject_list_requires_login(self):
		response = self.client.get(reverse("academics:subject-list"))
		self.assertEqual(response.status_code, 302)

	def test_timetable_list_requires_login(self):
		response = self.client.get(reverse("academics:timetable-list"))
		self.assertEqual(response.status_code, 302)

	def test_grade_list_requires_login(self):
		response = self.client.get(reverse("academics:grade-list"))
		self.assertEqual(response.status_code, 302)

	def test_admin_can_access_all_list_views(self):
		self.login(self.admin_user)
		for url_name in (
			"academics:classsection-list",
			"academics:subject-list",
			"academics:timetable-list",
			"academics:grade-list",
			"academics:teacher-list",
		):
			with self.subTest(url_name=url_name):
				self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

	def test_teacher_can_access_all_list_views(self):
		self.login(self.teacher_user)
		for url_name in (
			"academics:classsection-list",
			"academics:subject-list",
			"academics:timetable-list",
			"academics:grade-list",
		):
			with self.subTest(url_name=url_name):
				self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

	def test_teacher_role_denied_on_teacher_list(self):
		self.login(self.teacher_user)
		self.assertEqual(self.client.get(reverse("academics:teacher-list")).status_code, 403)

	def test_student_role_denied_on_list_views(self):
		self.login(self.student_user)
		for url_name in (
			"academics:classsection-list",
			"academics:subject-list",
			"academics:timetable-list",
			"academics:grade-list",
			"academics:teacher-list",
		):
			with self.subTest(url_name=url_name):
				self.assertEqual(self.client.get(reverse(url_name)).status_code, 403)

	def test_parent_role_denied_on_list_views(self):
		self.login(self.parent_user)
		for url_name in (
			"academics:classsection-list",
			"academics:subject-list",
			"academics:timetable-list",
			"academics:grade-list",
			"academics:teacher-list",
		):
			with self.subTest(url_name=url_name):
				self.assertEqual(self.client.get(reverse(url_name)).status_code, 403)

	def test_teacher_denied_classsection_create(self):
		self.login(self.teacher_user)
		self.assertEqual(self.client.get(reverse("academics:classsection-create")).status_code, 403)

	def test_teacher_denied_subject_create(self):
		self.login(self.teacher_user)
		self.assertEqual(self.client.get(reverse("academics:subject-create")).status_code, 403)

	def test_teacher_denied_timetable_create(self):
		self.login(self.teacher_user)
		self.assertEqual(self.client.get(reverse("academics:timetable-create")).status_code, 403)

	def test_admin_can_access_classsection_create(self):
		self.login(self.admin_user)
		self.assertEqual(self.client.get(reverse("academics:classsection-create")).status_code, 200)

	def test_admin_can_access_subject_create(self):
		self.login(self.admin_user)
		self.assertEqual(self.client.get(reverse("academics:subject-create")).status_code, 200)

	def test_admin_can_access_timetable_create(self):
		self.login(self.admin_user)
		self.assertEqual(self.client.get(reverse("academics:timetable-create")).status_code, 200)

	def test_teacher_can_access_grade_create(self):
		self.login(self.teacher_user)
		self.assertEqual(self.client.get(reverse("academics:grade-create")).status_code, 200)

	def test_teacher_can_access_grade_update(self):
		self.login(self.teacher_user)
		self.assertEqual(
			self.client.get(reverse("academics:grade-update", args=[self.grade_result.pk])).status_code,
			200,
		)


# ---------------------------------------------------------------------------
# CRUD tests — admin writes
# ---------------------------------------------------------------------------

class AcademicsAdminWriteTests(AcademicsModuleTestCase):

	def test_admin_can_create_subject(self):
		self.login(self.admin_user)
		response = self.client.post(
			reverse("academics:subject-create"),
			{
				"school": self.school.pk,
				"name": "Chemistry",
				"code": "CHE",
				"description": "",
				"is_optional": False,
				"is_active": True,
			},
		)
		self.assertRedirects(response, reverse("academics:subject-list"))
		self.assertTrue(Subject.objects.filter(school=self.school, code="CHE").exists())

	def test_admin_can_update_subject(self):
		self.login(self.admin_user)
		response = self.client.post(
			reverse("academics:subject-update", args=[self.subject.pk]),
			{
				"school": self.school.pk,
				"name": "Biology Updated",
				"code": "BIO",
				"description": "Updated description",
				"is_optional": False,
				"is_active": True,
			},
		)
		self.assertRedirects(response, reverse("academics:subject-list"))
		self.subject.refresh_from_db()
		self.assertEqual(self.subject.name, "Biology Updated")

	def test_admin_can_create_classsection(self):
		self.login(self.admin_user)
		response = self.client.post(
			reverse("academics:classsection-create"),
			{
				"school": self.school.pk,
				"academic_year": self.academic_year.pk,
				"grade_level": "Form 3",
				"stream": "A",
				"capacity": 35,
				"room_name": "Room 12",
				"homeroom_teacher": "",
				"notes": "",
			},
		)
		self.assertRedirects(response, reverse("academics:classsection-list"))
		self.assertTrue(
			ClassSection.objects.filter(school=self.school, grade_level="Form 3", stream="A").exists()
		)

	def test_admin_can_create_timetable_entry(self):
		self.login(self.admin_user)
		response = self.client.post(
			reverse("academics:timetable-create"),
			{
				"school": self.school.pk,
				"term": self.term.pk,
				"teaching_assignment": self.assignment.pk,
				"weekday": TimetableEntry.Weekday.TUESDAY,
				"start_time": "10:00",
				"end_time": "11:00",
				"room_name": "Lab 1",
				"period_label": "P2",
				"notes": "",
			},
		)
		self.assertRedirects(response, reverse("academics:timetable-list"))
		self.assertTrue(
			TimetableEntry.objects.filter(
				school=self.school,
				weekday=TimetableEntry.Weekday.TUESDAY,
				period_label="P2",
			).exists()
		)


# ---------------------------------------------------------------------------
# Grade result — teacher write tests
# ---------------------------------------------------------------------------

class AcademicsGradeWriteTests(AcademicsModuleTestCase):

	def test_teacher_can_create_grade_result(self):
		self.login(self.teacher_user)
		user2 = User.objects.create_user(
			username="student.academics.2",
			email="student.academics.2@example.com",
			password="TestPass1234",
			role=User.Role.STUDENT,
		)
		sync_role_group_membership(user2)
		student2 = Student.objects.create(
			school=self.school,
			user=user2,
			admission_number="ACA-002",
			admission_date=datetime.date(2026, 1, 9),
		)
		enrollment2 = Enrollment.objects.create(
			school=self.school,
			student=student2,
			academic_year=self.academic_year,
			term=self.term,
			class_section=self.section,
			status=Enrollment.Status.ACTIVE,
			start_date=self.term.start_date,
			roll_number=2,
		)
		response = self.client.post(
			reverse("academics:grade-create"),
			{
				"enrollment": enrollment2.pk,
				"subject": self.subject.pk,
				"score": "72.00",
				"grade": "B",
				"remarks": "",
			},
		)
		self.assertRedirects(response, reverse("academics:grade-list"))
		gr = GradeResult.objects.get(enrollment=enrollment2, subject=self.subject)
		self.assertEqual(gr.recorded_by, self.teacher_user)
		self.assertEqual(gr.grade, "B")

	def test_teacher_can_update_grade_result(self):
		self.login(self.teacher_user)
		response = self.client.post(
			reverse("academics:grade-update", args=[self.grade_result.pk]),
			{
				"enrollment": self.enrollment.pk,
				"subject": self.subject.pk,
				"score": "90.00",
				"grade": "A+",
				"remarks": "Excellent",
			},
		)
		self.assertRedirects(response, reverse("academics:grade-list"))
		self.grade_result.refresh_from_db()
		self.assertEqual(self.grade_result.grade, "A+")

	def test_teacher_cannot_create_grade_for_unassigned_subject(self):
		self.login(self.teacher_user)
		other_subject = Subject.objects.create(
			school=self.school,
			name="Chemistry",
			code="CHE",
		)
		user2 = User.objects.create_user(
			username="student.academics.3",
			email="student.academics.3@example.com",
			password="TestPass1234",
			role=User.Role.STUDENT,
			school=self.school,
		)
		sync_role_group_membership(user2)
		student2 = Student.objects.create(
			school=self.school,
			user=user2,
			admission_number="ACA-003",
			admission_date=datetime.date(2026, 1, 9),
		)
		enrollment2 = Enrollment.objects.create(
			school=self.school,
			student=student2,
			academic_year=self.academic_year,
			term=self.term,
			class_section=self.section,
			status=Enrollment.Status.ACTIVE,
			start_date=self.term.start_date,
			roll_number=3,
		)

		response = self.client.post(
			reverse("academics:grade-create"),
			{
				"enrollment": enrollment2.pk,
				"subject": other_subject.pk,
				"score": "68.00",
				"grade": "C",
				"remarks": "Denied test",
			},
		)
		self.assertEqual(response.status_code, 403)

	def test_teacher_cannot_create_grade_for_unassigned_class(self):
		self.login(self.teacher_user)
		other_section = ClassSection.objects.create(
			school=self.school,
			academic_year=self.academic_year,
			grade_level="Form 4",
			stream="A",
			capacity=35,
		)
		user2 = User.objects.create_user(
			username="student.academics.4",
			email="student.academics.4@example.com",
			password="TestPass1234",
			role=User.Role.STUDENT,
			school=self.school,
		)
		sync_role_group_membership(user2)
		student2 = Student.objects.create(
			school=self.school,
			user=user2,
			admission_number="ACA-004",
			admission_date=datetime.date(2026, 1, 9),
		)
		enrollment2 = Enrollment.objects.create(
			school=self.school,
			student=student2,
			academic_year=self.academic_year,
			term=self.term,
			class_section=other_section,
			status=Enrollment.Status.ACTIVE,
			start_date=self.term.start_date,
			roll_number=4,
		)

		response = self.client.post(
			reverse("academics:grade-create"),
			{
				"enrollment": enrollment2.pk,
				"subject": self.subject.pk,
				"score": "77.00",
				"grade": "B-",
				"remarks": "Denied test",
			},
		)
		self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Search / filter tests
# ---------------------------------------------------------------------------

class AcademicsFilterTests(AcademicsModuleTestCase):

	def test_classsection_list_filter_by_school(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:classsection-list"), {"school": self.school.pk})
		self.assertEqual(response.status_code, 200)
		self.assertIn(self.section, response.context["sections"])

	def test_subject_list_search(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:subject-list"), {"q": "Biology"})
		self.assertEqual(response.status_code, 200)
		subjects = list(response.context["subjects"])
		self.assertTrue(any(s.code == "BIO" for s in subjects))

	def test_timetable_list_filter_by_weekday(self):
		self.login(self.admin_user)
		response = self.client.get(
			reverse("academics:timetable-list"),
			{"weekday": TimetableEntry.Weekday.MONDAY},
		)
		self.assertEqual(response.status_code, 200)
		self.assertIn(self.timetable_entry, response.context["entries"])

	def test_grade_list_filter_by_subject(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:grade-list"), {"subject": self.subject.pk})
		self.assertEqual(response.status_code, 200)
		self.assertIn(self.grade_result, response.context["results"])


# ---------------------------------------------------------------------------
# HTMX partial response tests
# ---------------------------------------------------------------------------

class AcademicsHtmxTests(AcademicsModuleTestCase):

	HTMX_HEADERS = {"HTTP_HX_REQUEST": "true"}

	def test_classsection_list_htmx_returns_partial(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:classsection-list"), **self.HTMX_HEADERS)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "academics/partials/classsection_results.html")

	def test_subject_list_htmx_returns_partial(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:subject-list"), **self.HTMX_HEADERS)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "academics/partials/subject_results.html")

	def test_teacher_list_htmx_returns_partial(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:teacher-list"), **self.HTMX_HEADERS)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "academics/partials/teacher_results.html")

	def test_timetable_list_htmx_returns_partial(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:timetable-list"), **self.HTMX_HEADERS)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "academics/partials/timetable_results.html")

	def test_grade_list_htmx_returns_partial(self):
		self.login(self.admin_user)
		response = self.client.get(reverse("academics:grade-list"), **self.HTMX_HEADERS)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "academics/partials/grade_results.html")

	def test_classsection_list_boosted_htmx_returns_full_page(self):
		self.login(self.admin_user)
		response = self.client.get(
			reverse("academics:classsection-list"),
			HTTP_HX_REQUEST="true",
			HTTP_HX_BOOSTED="true",
		)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "academics/classsection_list.html")


# ---------------------------------------------------------------------------
# Timetable overlap validation
# ---------------------------------------------------------------------------

class TimetableOverlapTests(AcademicsModuleTestCase):

	def test_timetable_entry_clean_rejects_overlap_same_class(self):
		from django.core.exceptions import ValidationError

		duplicate = TimetableEntry(
			school=self.school,
			term=self.term,
			teaching_assignment=self.assignment,
			weekday=TimetableEntry.Weekday.MONDAY,
			start_time=datetime.time(8, 30),
			end_time=datetime.time(9, 30),
		)
		with self.assertRaises(ValidationError):
			duplicate.clean()

	def test_timetable_entry_clean_passes_different_weekday(self):
		from django.core.exceptions import ValidationError

		entry = TimetableEntry(
			school=self.school,
			term=self.term,
			teaching_assignment=self.assignment,
			weekday=TimetableEntry.Weekday.WEDNESDAY,
			start_time=datetime.time(8, 0),
			end_time=datetime.time(9, 0),
		)
		try:
			entry.clean()
		except ValidationError:
			self.fail("clean() raised ValidationError for a non-overlapping entry")

	def test_timetable_entry_clean_rejects_end_before_start(self):
		from django.core.exceptions import ValidationError

		entry = TimetableEntry(
			school=self.school,
			term=self.term,
			teaching_assignment=self.assignment,
			weekday=TimetableEntry.Weekday.FRIDAY,
			start_time=datetime.time(10, 0),
			end_time=datetime.time(9, 0),
		)
		with self.assertRaises(ValidationError):
			entry.clean()
