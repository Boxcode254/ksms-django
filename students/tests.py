from datetime import date

from django.db import connection
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassSection, Teacher, Term
from core.models import School, User
from core.signals import sync_role_group_membership

from .models import Enrollment, Guardian, Student, StudentGuardianRelationship


class StudentModuleTestCase(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.school = School.objects.create(
			name="KSMS Test School",
			code="TESTSCH",
			slug="ksms-test-school",
			email="info@testschool.example.com",
			phone="+254700000001",
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

		cls.teacher_user = User.objects.create_user(
			username="teacher.module1",
			email="teacher.module1@example.com",
			password="ChangeMe12345!",
			role=User.Role.TEACHER,
			school=cls.school,
			first_name="Module",
			last_name="Teacher",
		)
		sync_role_group_membership(cls.teacher_user)
		cls.teacher_profile = Teacher.objects.create(
			school=cls.school,
			user=cls.teacher_user,
			employee_number="TCHR-M1",
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

		cls.admin_user = User.objects.create_user(
			username="admin.module1",
			email="admin.module1@example.com",
			password="ChangeMe12345!",
			role=User.Role.SCHOOL_ADMIN,
			school=cls.school,
			first_name="Module",
			last_name="Admin",
		)
		sync_role_group_membership(cls.admin_user)

		cls.student_user = User.objects.create_user(
			username="student.module1",
			email="student.module1@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			school=cls.school,
			first_name="Ada",
			last_name="Student",
		)
		sync_role_group_membership(cls.student_user)
		cls.student = Student.objects.create(
			school=cls.school,
			user=cls.student_user,
			admission_number="ADM-001",
			admission_date=date(2026, 1, 9),
			status=Student.Status.ACTIVE,
		)

		cls.guardian_user = User.objects.create_user(
			username="guardian.module1",
			email="guardian.module1@example.com",
			password="ChangeMe12345!",
			role=User.Role.PARENT,
			school=cls.school,
			first_name="Grace",
			last_name="Guardian",
		)
		sync_role_group_membership(cls.guardian_user)
		cls.guardian = Guardian.objects.create(
			school=cls.school,
			user=cls.guardian_user,
			occupation="Business Owner",
		)

		cls.relationship = StudentGuardianRelationship.objects.create(
			student=cls.student,
			guardian=cls.guardian,
			relationship=StudentGuardianRelationship.Relationship.MOTHER,
			is_primary_contact=True,
			is_emergency_contact=True,
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

	def login_admin(self):
		self.client.force_login(self.admin_user)

	def login_teacher(self):
		self.client.force_login(self.teacher_user)


class StudentModulePermissionTests(StudentModuleTestCase):
	def test_student_list_requires_login(self):
		response = self.client.get(reverse("students:student-list"))
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("account_login"), response.url)

	def test_teacher_has_read_only_access(self):
		self.login_teacher()
		self.assertEqual(self.client.get(reverse("students:student-list")).status_code, 200)
		self.assertEqual(self.client.get(reverse("students:guardian-list")).status_code, 200)
		self.assertEqual(self.client.get(reverse("students:student-detail", kwargs={"pk": self.student.pk})).status_code, 200)
		self.assertEqual(self.client.get(reverse("students:student-create")).status_code, 403)
		self.assertEqual(self.client.get(reverse("students:guardian-create")).status_code, 403)

	def test_admin_has_write_access(self):
		self.login_admin()
		self.assertEqual(self.client.get(reverse("students:student-create")).status_code, 200)
		self.assertEqual(self.client.get(reverse("students:guardian-create")).status_code, 200)

	def test_school_admin_only_sees_students_for_own_school(self):
		other_school = School.objects.create(
			name="KSMS Other School",
			code="OTHERSCH",
			slug="ksms-other-school",
			email="other@example.com",
			phone="+254700000099",
		)
		other_user = User.objects.create_user(
			username="student.other",
			email="student.other@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			school=other_school,
		)
		Student.objects.create(
			school=other_school,
			user=other_user,
			admission_number="ADM-999",
			admission_date=date(2026, 1, 9),
		)

		self.login_admin()
		response = self.client.get(reverse("students:student-list"))

		self.assertEqual(response.status_code, 200)
		self.assertQuerySetEqual(
			response.context["students"],
			[repr(self.student)],
			transform=repr,
			ordered=False,
		)

	def test_school_admin_cannot_open_student_detail_from_other_school(self):
		other_school = School.objects.create(
			name="KSMS Detail School",
			code="DETAILSCH",
			slug="ksms-detail-school",
			email="detail@example.com",
			phone="+254700000098",
		)
		other_user = User.objects.create_user(
			username="student.detail.other",
			email="student.detail.other@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			school=other_school,
		)
		other_student = Student.objects.create(
			school=other_school,
			user=other_user,
			admission_number="ADM-998",
			admission_date=date(2026, 1, 9),
		)

		self.login_admin()
		response = self.client.get(reverse("students:student-detail", kwargs={"pk": other_student.pk}))

		self.assertEqual(response.status_code, 404)


class StudentModuleCrudTests(StudentModuleTestCase):
	def test_admin_can_create_student_with_linked_user(self):
		self.login_admin()
		response = self.client.post(
			reverse("students:student-create"),
			{
				"school": self.school.pk,
				"username": "student.new",
				"first_name": "New",
				"last_name": "Learner",
				"email": "student.new@example.com",
				"phone": "+254700000010",
				"is_active": "on",
				"password1": "ChangeMe12345!",
				"password2": "ChangeMe12345!",
				"admission_number": "ADM-010",
				"date_of_birth": "2012-05-01",
				"gender": Student.Gender.FEMALE,
				"admission_date": "2026-05-05",
				"status": Student.Status.ACTIVE,
				"address": "Nairobi",
				"notes": "Created in test.",
			},
		)
		self.assertEqual(response.status_code, 302)
		created_student = Student.objects.get(admission_number="ADM-010")
		self.assertEqual(created_student.user.role, User.Role.STUDENT)
		self.assertEqual(created_student.user.email, "student.new@example.com")

	def test_admin_can_create_guardian_with_linked_user(self):
		self.login_admin()
		response = self.client.post(
			reverse("students:guardian-create"),
			{
				"school": self.school.pk,
				"username": "guardian.new",
				"first_name": "New",
				"last_name": "Guardian",
				"email": "guardian.new@example.com",
				"phone": "+254700000011",
				"is_active": "on",
				"password1": "ChangeMe12345!",
				"password2": "ChangeMe12345!",
				"occupation": "Teacher",
				"national_id": "99887766",
				"postal_address": "Nakuru",
				"notes": "Created in test.",
			},
		)
		self.assertEqual(response.status_code, 302)
		created_guardian = Guardian.objects.get(user__username="guardian.new")
		self.assertEqual(created_guardian.user.role, User.Role.PARENT)

	def test_admin_can_link_existing_guardian_to_student(self):
		self.login_admin()
		other_guardian_user = User.objects.create_user(
			username="guardian.extra",
			email="guardian.extra@example.com",
			password="ChangeMe12345!",
			role=User.Role.PARENT,
			first_name="Extra",
			last_name="Guardian",
		)
		sync_role_group_membership(other_guardian_user)
		other_guardian = Guardian.objects.create(school=self.school, user=other_guardian_user)

		response = self.client.post(
			reverse("students:relationship-create", kwargs={"student_pk": self.student.pk}),
			{
				"student": self.student.pk,
				"guardian": other_guardian.pk,
				"relationship": StudentGuardianRelationship.Relationship.GUARDIAN,
				"is_emergency_contact": "on",
				"is_fee_payer": "on",
				"notes": "Linked in test.",
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(
			StudentGuardianRelationship.objects.filter(student=self.student, guardian=other_guardian).exists()
		)

	def test_admin_can_create_enrollment(self):
		self.login_admin()
		other_student_user = User.objects.create_user(
			username="student.extra",
			email="student.extra@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			first_name="Extra",
			last_name="Student",
		)
		sync_role_group_membership(other_student_user)
		other_student = Student.objects.create(
			school=self.school,
			user=other_student_user,
			admission_number="ADM-050",
			admission_date=date(2026, 1, 9),
		)

		response = self.client.post(
			reverse("students:enrollment-create", kwargs={"student_pk": other_student.pk}),
			{
				"school": self.school.pk,
				"student": other_student.pk,
				"academic_year": self.academic_year.pk,
				"term": self.term.pk,
				"class_section": self.class_section.pk,
				"status": Enrollment.Status.ACTIVE,
				"start_date": self.term.start_date,
				"end_date": "",
				"roll_number": 2,
				"notes": "Created in test.",
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(Enrollment.objects.filter(student=other_student, term=self.term).exists())


class StudentModuleListTests(StudentModuleTestCase):
	@classmethod
	def setUpTestData(cls):
		super().setUpTestData()
		for index in range(2, 14):
			user = User.objects.create_user(
				username=f"student.bulk{index}",
				email=f"student.bulk{index}@example.com",
				password="ChangeMe12345!",
				role=User.Role.STUDENT,
				first_name=f"Bulk{index}",
				last_name="Student",
			)
			sync_role_group_membership(user)
			student = Student.objects.create(
				school=cls.school,
				user=user,
				admission_number=f"ADM-{index:03d}",
				admission_date=date(2026, 1, 9),
				status=Student.Status.SUSPENDED if index % 2 == 0 else Student.Status.ACTIVE,
			)
			Enrollment.objects.create(
				school=cls.school,
				student=student,
				academic_year=cls.academic_year,
				term=cls.term,
				class_section=cls.class_section,
				status=Enrollment.Status.ACTIVE,
				start_date=cls.term.start_date,
				roll_number=index,
			)

	def test_student_list_search_filter_and_pagination(self):
		self.login_teacher()
		response = self.client.get(
			reverse("students:student-list"),
			{"q": "Ada", "status": Student.Status.ACTIVE, "page": 1},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "ADM-001")
		self.assertNotContains(response, "ADM-002")

		response = self.client.get(reverse("students:student-list"), {"page": 2})
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["is_paginated"])

	def test_student_list_htmx_returns_partial(self):
		self.login_teacher()
		response = self.client.get(
			reverse("students:student-list"),
			{"q": "ADM-001"},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "students/partials/student_results.html")
		self.assertNotContains(response, "<!DOCTYPE html>", html=False)

	def test_guardian_list_htmx_returns_partial(self):
		self.login_teacher()
		response = self.client.get(reverse("students:guardian-list"), HTTP_HX_REQUEST="true")
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "students/partials/guardian_results.html")

	def test_student_list_boosted_htmx_returns_full_page(self):
		self.login_teacher()
		response = self.client.get(
			reverse("students:student-list"),
			HTTP_HX_REQUEST="true",
			HTTP_HX_BOOSTED="true",
		)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "students/student_list.html")


class GuardianNationalIdSecurityTests(StudentModuleTestCase):
	def test_guardian_national_id_encrypted_at_rest(self):
		self.guardian.national_id = "99887766"
		self.guardian.save()

		with connection.cursor() as cursor:
			cursor.execute(
				"SELECT national_id FROM students_guardian WHERE id = %s",
				[self.guardian.pk],
			)
			raw_value = cursor.fetchone()[0]
		self.assertNotEqual(raw_value, "99887766")
		self.assertEqual(Guardian.objects.get(pk=self.guardian.pk).national_id, "99887766")
		self.assertTrue(Guardian.objects.filter(pk=self.guardian.pk, national_id_fingerprint__isnull=False).exists())

	def test_guardian_detail_masks_national_id(self):
		self.guardian.national_id = "99887766"
		self.guardian.save()
		self.login_teacher()

		response = self.client.get(reverse("students:guardian-detail", kwargs={"pk": self.guardian.pk}))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "9988XXXX")
		self.assertNotContains(response, "99887766")

	def test_student_model_does_not_have_national_id_field(self):
		self.assertFalse(any(field.name == "national_id" for field in Student._meta.get_fields()))


class StudentTeacherVisibilityTests(StudentModuleTestCase):
	"""Teacher-scoped student and guardian visibility enforcement."""

	@classmethod
	def setUpTestData(cls):
		super().setUpTestData()

		# A second school + student to confirm cross-school isolation still works.
		cls.other_school = School.objects.create(
			name="Other School",
			code="OTHSCH",
			slug="other-school",
			email="info@other.example.com",
			phone="+254700000099",
			county="Mombasa",
		)
		cls.other_student_user = User.objects.create_user(
			username="student.other",
			email="student.other@example.com",
			password="ChangeMe12345!",
			role=User.Role.STUDENT,
			school=cls.other_school,
			first_name="Bob",
			last_name="Other",
		)
		sync_role_group_membership(cls.other_student_user)
		cls.other_student = Student.objects.create(
			school=cls.other_school,
			user=cls.other_student_user,
			admission_number="ADM-OTHER-001",
			admission_date=date(2026, 1, 9),
			status=Student.Status.ACTIVE,
		)

		# An unassigned teacher who has no class assignments.
		cls.unassigned_teacher_user = User.objects.create_user(
			username="teacher.unassigned",
			email="teacher.unassigned@example.com",
			password="ChangeMe12345!",
			role=User.Role.TEACHER,
			school=cls.school,
			first_name="New",
			last_name="Teacher",
		)
		sync_role_group_membership(cls.unassigned_teacher_user)
		Teacher.objects.create(
			school=cls.school,
			user=cls.unassigned_teacher_user,
			employee_number="TCHR-U1",
			hire_date=date(2026, 1, 7),
		)

	def test_teacher_homeroom_sees_enrolled_student_in_list(self):
		"""Homeroom teacher can see the student list because student is enrolled in their class."""
		self.login_teacher()
		response = self.client.get(reverse("students:student-list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.student.admission_number)

	def test_teacher_homeroom_sees_guardian_linked_to_enrolled_student(self):
		"""Teacher can see guardian whose student is in their homeroom class."""
		self.login_teacher()
		response = self.client.get(reverse("students:guardian-list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.guardian_user.first_name)

	def test_teacher_homeroom_can_access_enrolled_student_detail(self):
		"""Teacher can view detail page for a student in their homeroom class."""
		self.login_teacher()
		response = self.client.get(reverse("students:student-detail", kwargs={"pk": self.student.pk}))
		self.assertEqual(response.status_code, 200)

	def test_teacher_homeroom_can_access_guardian_detail(self):
		"""Teacher can view detail page for guardian whose student is in their class."""
		self.login_teacher()
		response = self.client.get(reverse("students:guardian-detail", kwargs={"pk": self.guardian.pk}))
		self.assertEqual(response.status_code, 200)

	def test_unassigned_teacher_sees_empty_student_list(self):
		"""Teacher with no class assignments sees no students."""
		self.client.force_login(self.unassigned_teacher_user)
		response = self.client.get(reverse("students:student-list"))
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, self.student.admission_number)

	def test_unassigned_teacher_cannot_access_student_detail(self):
		"""Teacher with no assignments gets 404 for any student detail page."""
		self.client.force_login(self.unassigned_teacher_user)
		response = self.client.get(reverse("students:student-detail", kwargs={"pk": self.student.pk}))
		self.assertEqual(response.status_code, 404)

	def test_teacher_with_assigned_class_sees_enrolled_student(self):
		"""Teacher can see student after being added to assigned_classes M2M."""
		self.client.force_login(self.unassigned_teacher_user)
		teacher_profile = Teacher.objects.get(user=self.unassigned_teacher_user)
		teacher_profile.assigned_classes.add(self.class_section)
		try:
			response = self.client.get(reverse("students:student-list"))
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, self.student.admission_number)
		finally:
			teacher_profile.assigned_classes.remove(self.class_section)

	def test_school_admin_sees_all_students_in_school(self):
		"""School admin sees all students in their school, not those of other schools."""
		self.login_admin()
		response = self.client.get(reverse("students:student-list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.student.admission_number)
		self.assertNotContains(response, self.other_student.admission_number)

	def test_teacher_cannot_access_student_from_other_school(self):
		"""Teacher gets 404 when trying to access a student from another school."""
		self.login_teacher()
		response = self.client.get(reverse("students:student-detail", kwargs={"pk": self.other_student.pk}))
		self.assertEqual(response.status_code, 404)
