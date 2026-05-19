from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassSection, Subject, Teacher, TeachingAssignment, Term
from core.models import School, User
from core.signals import sync_role_group_membership
from students.models import Enrollment, Student

from .models import AttendanceStatus, DailyAttendance, PeriodAttendance


class AttendanceModuleTestCase(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.school = School.objects.create(
			name="KSMS Attendance School",
			code="ATTSCH",
			slug="ksms-attendance-school",
			email="attendance@testschool.example.com",
			phone="+254700000021",
			county="Nairobi",
		)
		cls.academic_year = AcademicYear.objects.create(
			school=cls.school,
			name="2026",
			start_date=date(2026, 1, 5),
			end_date=date(2026, 11, 20),
			is_current=True,
		)
		cls.term = Term.objects.create(
			school=cls.school,
			academic_year=cls.academic_year,
			name=Term.Name.TERM_2,
			start_date=date(2026, 5, 4),
			end_date=date(2026, 8, 14),
			is_current=True,
		)
		cls.admin_user = User.objects.create_user(
			username="admin.attendance",
			email="admin.attendance@example.com",
			password="ChangeMe12345!",
			role=User.Role.SCHOOL_ADMIN,
			school=cls.school,
			first_name="Attendance",
			last_name="Admin",
		)
		sync_role_group_membership(cls.admin_user)
		cls.teacher_user = User.objects.create_user(
			username="teacher.attendance",
			email="teacher.attendance@example.com",
			password="ChangeMe12345!",
			role=User.Role.TEACHER,
			school=cls.school,
			first_name="Attendance",
			last_name="Teacher",
		)
		sync_role_group_membership(cls.teacher_user)
		cls.teacher_profile = Teacher.objects.create(
			school=cls.school,
			user=cls.teacher_user,
			employee_number="TCHR-ATT-01",
			hire_date=date(2026, 1, 7),
		)
		cls.class_section = ClassSection.objects.create(
			school=cls.school,
			academic_year=cls.academic_year,
			grade_level="Form 1",
			stream="A",
			homeroom_teacher=cls.teacher_profile,
			capacity=40,
		)
		cls.subject = Subject.objects.create(
			school=cls.school,
			name="Mathematics",
			code="MAT",
			is_active=True,
		)
		cls.other_class_section = ClassSection.objects.create(
			school=cls.school,
			academic_year=cls.academic_year,
			grade_level="Form 1",
			stream="B",
			capacity=40,
		)
		cls.other_subject = Subject.objects.create(
			school=cls.school,
			name="History",
			code="HIS",
			is_active=True,
		)
		TeachingAssignment.objects.create(
			school=cls.school,
			class_section=cls.class_section,
			subject=cls.subject,
			teacher=cls.teacher_profile,
		)

		cls.student_user = User.objects.create_user(
			username="student.attendance",
			email="student.attendance@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			first_name="Amina",
			last_name="Learner",
		)
		sync_role_group_membership(cls.student_user)
		cls.student = Student.objects.create(
			school=cls.school,
			user=cls.student_user,
			admission_number="ATT-001",
			admission_date=date(2026, 1, 9),
		)
		cls.enrollment = Enrollment.objects.create(
			school=cls.school,
			student=cls.student,
			academic_year=cls.academic_year,
			term=cls.term,
			class_section=cls.class_section,
			status=Enrollment.Status.ACTIVE,
			start_date=cls.term.start_date,
			roll_number=1,
		)
		cls.other_student_user = User.objects.create_user(
			username="student.attendance.unauth",
			email="student.attendance.unauth@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			school=cls.school,
		)
		sync_role_group_membership(cls.other_student_user)
		cls.other_student = Student.objects.create(
			school=cls.school,
			user=cls.other_student_user,
			admission_number="ATT-099",
			admission_date=date(2026, 1, 9),
		)
		cls.other_enrollment = Enrollment.objects.create(
			school=cls.school,
			student=cls.other_student,
			academic_year=cls.academic_year,
			term=cls.term,
			class_section=cls.other_class_section,
			status=Enrollment.Status.ACTIVE,
			start_date=cls.term.start_date,
			roll_number=99,
		)
		cls.daily_attendance = DailyAttendance.objects.create(
			enrollment=cls.enrollment,
			attendance_date=cls.term.start_date,
			status=AttendanceStatus.PRESENT,
			recorded_by=cls.teacher_user,
		)
		cls.period_attendance = PeriodAttendance.objects.create(
			enrollment=cls.enrollment,
			subject=cls.subject,
			attendance_date=cls.term.start_date,
			period_number=1,
			status=AttendanceStatus.LATE,
			recorded_by=cls.teacher_user,
		)

	def login_teacher(self):
		self.client.force_login(self.teacher_user)

	def login_admin(self):
		self.client.force_login(self.admin_user)


class AttendanceModulePermissionTests(AttendanceModuleTestCase):
	def test_daily_list_requires_login(self):
		response = self.client.get(reverse("attendance:daily-list"))
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("account_login"), response.url)

	def test_teacher_can_access_attendance_views(self):
		self.login_teacher()
		self.assertEqual(self.client.get(reverse("attendance:daily-list")).status_code, 200)
		self.assertEqual(self.client.get(reverse("attendance:period-list")).status_code, 200)
		self.assertEqual(self.client.get(reverse("attendance:daily-create")).status_code, 200)
		self.assertEqual(self.client.get(reverse("attendance:period-create")).status_code, 200)

	def test_parent_role_is_denied(self):
		parent_user = User.objects.create_user(
			username="parent.attendance",
			email="parent.attendance@example.com",
			password="ChangeMe12345!",
			role=User.Role.PARENT,
		)
		sync_role_group_membership(parent_user)
		self.client.force_login(parent_user)
		response = self.client.get(reverse("attendance:daily-list"))
		self.assertEqual(response.status_code, 403)


class AttendanceModuleCrudTests(AttendanceModuleTestCase):
	def test_teacher_can_create_daily_attendance(self):
		self.login_teacher()
		extra_user = User.objects.create_user(
			username="student.attendance.2",
			email="student.attendance.2@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			first_name="Baraka",
			last_name="Learner",
		)
		sync_role_group_membership(extra_user)
		extra_student = Student.objects.create(
			school=self.school,
			user=extra_user,
			admission_number="ATT-002",
			admission_date=date(2026, 1, 9),
		)
		extra_enrollment = Enrollment.objects.create(
			school=self.school,
			student=extra_student,
			academic_year=self.academic_year,
			term=self.term,
			class_section=self.class_section,
			status=Enrollment.Status.ACTIVE,
			start_date=self.term.start_date,
			roll_number=2,
		)

		response = self.client.post(
			reverse("attendance:daily-create"),
			{
				"enrollment": extra_enrollment.pk,
				"attendance_date": self.term.start_date,
				"status": AttendanceStatus.ABSENT,
				"remarks": "Absent in test.",
			},
		)
		self.assertEqual(response.status_code, 302)
		created = DailyAttendance.objects.get(enrollment=extra_enrollment, attendance_date=self.term.start_date)
		self.assertEqual(created.recorded_by, self.teacher_user)
		self.assertEqual(created.status, AttendanceStatus.ABSENT)

	def test_teacher_can_create_period_attendance(self):
		self.login_teacher()
		response = self.client.post(
			reverse("attendance:period-create"),
			{
				"enrollment": self.enrollment.pk,
				"subject": self.subject.pk,
				"attendance_date": self.term.start_date + timedelta(days=1),
				"period_number": 2,
				"status": AttendanceStatus.PRESENT,
				"remarks": "Present in test.",
			},
		)
		self.assertEqual(response.status_code, 302)
		created = PeriodAttendance.objects.get(
			enrollment=self.enrollment,
			attendance_date=self.term.start_date + timedelta(days=1),
			period_number=2,
		)
		self.assertEqual(created.recorded_by, self.teacher_user)
		self.assertEqual(created.subject, self.subject)

	def test_teacher_cannot_mark_daily_register_for_unassigned_class(self):
		self.login_teacher()
		response = self.client.post(
			reverse("attendance:daily-create"),
			{
				"enrollment": self.other_enrollment.pk,
				"attendance_date": self.term.start_date,
				"status": AttendanceStatus.ABSENT,
				"remarks": "Denied test.",
			},
		)
		self.assertEqual(response.status_code, 403)
		self.assertFalse(
			DailyAttendance.objects.filter(
				enrollment=self.other_enrollment,
				attendance_date=self.term.start_date,
			).exists()
		)

	def test_teacher_cannot_mark_period_attendance_for_unassigned_subject(self):
		self.login_teacher()
		response = self.client.post(
			reverse("attendance:period-create"),
			{
				"enrollment": self.enrollment.pk,
				"subject": self.other_subject.pk,
				"attendance_date": self.term.start_date + timedelta(days=2),
				"period_number": 3,
				"status": AttendanceStatus.PRESENT,
				"remarks": "Denied test.",
			},
		)
		self.assertEqual(response.status_code, 403)

	def test_regular_teacher_assigned_class_cannot_submit_official_register_without_class_teacher_role(self):
		self.login_teacher()
		assigned_section = ClassSection.objects.create(
			school=self.school,
			academic_year=self.academic_year,
			grade_level="Form 2",
			stream="A",
			capacity=40,
		)
		assigned_student_user = User.objects.create_user(
			username="student.attendance.assigned",
			email="student.attendance.assigned@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
		)
		sync_role_group_membership(assigned_student_user)
		assigned_student = Student.objects.create(
			school=self.school,
			user=assigned_student_user,
			admission_number="ATT-200",
			admission_date=date(2026, 1, 9),
		)
		assigned_enrollment = Enrollment.objects.create(
			school=self.school,
			student=assigned_student,
			academic_year=self.academic_year,
			term=self.term,
			class_section=assigned_section,
			status=Enrollment.Status.ACTIVE,
			start_date=self.term.start_date,
			roll_number=200,
		)
		TeachingAssignment.objects.create(
			school=self.school,
			class_section=assigned_section,
			subject=self.subject,
			teacher=self.teacher_profile,
		)

		response = self.client.post(
			reverse("attendance:daily-list"),
			{
				"class_section": assigned_section.pk,
				"attendance_date": self.term.start_date.isoformat(),
				f"status_{assigned_enrollment.pk}": AttendanceStatus.PRESENT,
			},
		)
		self.assertEqual(response.status_code, 403)
		self.assertFalse(
			DailyAttendance.objects.filter(
				enrollment=assigned_enrollment,
				attendance_date=self.term.start_date,
			).exists()
		)

	def test_school_admin_can_submit_official_register_for_any_school_class(self):
		self.login_admin()
		response = self.client.post(
			reverse("attendance:daily-list"),
			{
				"class_section": self.other_class_section.pk,
				"attendance_date": self.term.start_date.isoformat(),
				f"status_{self.other_enrollment.pk}": AttendanceStatus.LATE,
			},
		)
		self.assertEqual(response.status_code, 302)
		record = DailyAttendance.objects.get(
			enrollment=self.other_enrollment,
			attendance_date=self.term.start_date,
		)
		self.assertEqual(record.status, AttendanceStatus.LATE)
		self.assertEqual(record.recorded_by, self.admin_user)


class AttendanceModuleListTests(AttendanceModuleTestCase):
	@classmethod
	def setUpTestData(cls):
		super().setUpTestData()
		for index in range(2, 23):
			user = User.objects.create_user(
				username=f"student.att.list{index}",
				email=f"student.att.list{index}@example.com",
				password="ChangeMe12345!",
				role=User.Role.STUDENT,
				first_name=f"List{index}",
				last_name="Learner",
			)
			sync_role_group_membership(user)
			student = Student.objects.create(
				school=cls.school,
				user=user,
				admission_number=f"ATT-{index:03d}",
				admission_date=date(2026, 1, 9),
			)
			enrollment = Enrollment.objects.create(
				school=cls.school,
				student=student,
				academic_year=cls.academic_year,
				term=cls.term,
				class_section=cls.class_section,
				status=Enrollment.Status.ACTIVE,
				start_date=cls.term.start_date,
				roll_number=index,
			)
			DailyAttendance.objects.create(
				enrollment=enrollment,
				attendance_date=cls.term.start_date,
				status=AttendanceStatus.ABSENT if index % 2 == 0 else AttendanceStatus.PRESENT,
				recorded_by=cls.teacher_user,
			)
			PeriodAttendance.objects.create(
				enrollment=enrollment,
				subject=cls.subject,
				attendance_date=cls.term.start_date,
				period_number=index % 4 + 1,
				status=AttendanceStatus.LATE if index % 2 == 0 else AttendanceStatus.PRESENT,
				recorded_by=cls.teacher_user,
			)

	def test_take_attendance_page_renders_new_template(self):
		self.login_teacher()
		response = self.client.get(reverse("attendance:daily-list"))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "attendance/take_attendance.html")
		self.assertContains(response, "Take Daily Class Attendance")

	def test_take_attendance_search_filters_student_roster(self):
		self.login_teacher()
		response = self.client.get(reverse("attendance:daily-list"), {"q": "ATT-001"})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "ATT-001")
		self.assertNotContains(response, "ATT-002")

	def test_daily_list_htmx_returns_partial(self):
		self.login_teacher()
		response = self.client.get(
			reverse("attendance:daily-list"),
			{"q": "ATT-001"},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "attendance/partials/take_attendance_content.html")

	def test_period_list_htmx_returns_partial(self):
		self.login_teacher()
		response = self.client.get(reverse("attendance:period-list"), HTTP_HX_REQUEST="true")
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "attendance/partials/period_results.html")

	def test_daily_list_boosted_htmx_returns_full_page(self):
		self.login_teacher()
		response = self.client.get(
			reverse("attendance:daily-list"),
			HTTP_HX_REQUEST="true",
			HTTP_HX_BOOSTED="true",
		)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "attendance/take_attendance.html")

	def test_regular_teacher_unassigned_class_shows_warning_and_no_roster(self):
		self.login_teacher()
		response = self.client.get(
			reverse("attendance:daily-list"),
			{"class_section": self.other_class_section.pk},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "You can only access classes assigned to your account.")
		self.assertContains(response, "Select a class to load learners.")
