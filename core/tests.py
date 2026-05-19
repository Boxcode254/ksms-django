from django.test import TestCase
from django.urls import reverse
from cryptography.fernet import InvalidToken

from academics.models import AcademicYear, ClassSection, Subject, Teacher
from .models import School, User
from .encryption import decrypt_value, encrypt_value, fingerprint_value, mask_identifier


class EncryptionUtilityTests(TestCase):
	def test_encrypt_and_decrypt_round_trip(self):
		plaintext = "99887766"
		encrypted = encrypt_value(plaintext)
		self.assertNotEqual(encrypted, plaintext)
		self.assertEqual(decrypt_value(encrypted), plaintext)

	def test_blank_and_null_values_are_passthrough(self):
		self.assertEqual(encrypt_value(""), "")
		self.assertIsNone(encrypt_value(None))
		self.assertEqual(decrypt_value(""), "")
		self.assertIsNone(decrypt_value(None))

	def test_decrypt_invalid_token_strict_mode_raises(self):
		with self.assertRaises(InvalidToken):
			decrypt_value("not-a-valid-token", strict=True)

	def test_fingerprint_is_stable_for_equivalent_values(self):
		one = fingerprint_value(" 9988 7766 ")
		two = fingerprint_value("99887766")
		self.assertEqual(one, two)

	def test_mask_identifier_masks_last_four_characters(self):
		self.assertEqual(mask_identifier("12345678"), "1234XXXX")


class PWAEndpointTests(TestCase):
	def test_manifest_returns_installable_payload(self):
		School.objects.create(
			name="Demo School",
			code="DEMO",
			slug="demo-school",
			email="demo@example.com",
			phone="+254700000000",
		)
		response = self.client.get(reverse("core:web-manifest"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "application/json")
		payload = response.json()
		self.assertEqual(payload["short_name"], "KSMS")
		self.assertEqual(payload["display"], "standalone")
		self.assertIn("Demo School", payload["name"])
		self.assertEqual(len(payload["icons"]), 2)

	def test_service_worker_js_is_served(self):
		response = self.client.get(reverse("core:service-worker"))
		self.assertEqual(response.status_code, 200)
		self.assertIn("application/javascript", response["Content-Type"])
		self.assertContains(response, "CACHE_NAME")


class UserRoleCompatibilityTests(TestCase):
	def test_legacy_admin_role_is_normalized_to_school_admin_on_save(self):
		school = School.objects.create(
			name="Compatibility School",
			code="COMPAT",
			slug="compatibility-school",
			email="compat@example.com",
			phone="+254700000021",
		)
		user = User.objects.create_user(
			username="legacy.admin",
			email="legacy.admin@example.com",
			password="ChangeMe12345!",
			role="admin",
			school=school,
		)

		user.refresh_from_db()
		self.assertEqual(user.role, User.Role.SCHOOL_ADMIN)
		self.assertFalse(user.is_superuser)
		self.assertFalse(user.is_staff)

	def test_school_admin_is_not_django_admin_staff(self):
		school = School.objects.create(
			name="Admin Access School",
			code="ADMINACC",
			slug="admin-access-school",
			email="adminacc@example.com",
			phone="+254700000022",
		)
		user = User.objects.create_user(
			username="school.admin.only",
			email="school.admin.only@example.com",
			password="ChangeMe12345!",
			role=User.Role.SCHOOL_ADMIN,
			school=school,
		)

		user.refresh_from_db()
		self.assertEqual(user.role, User.Role.SCHOOL_ADMIN)
		self.assertFalse(user.is_superuser)
		self.assertFalse(user.is_staff)

	def test_superuser_remains_django_admin_staff(self):
		user = User.objects.create_superuser(
			username="root.admin",
			email="root.admin@example.com",
			password="ChangeMe12345!",
		)

		user.refresh_from_db()
		self.assertEqual(user.role, User.Role.SUPERUSER)
		self.assertTrue(user.is_superuser)
		self.assertTrue(user.is_staff)


class DjangoAdminAccessTests(TestCase):
	def setUp(self):
		self.school = School.objects.create(
			name="Admin Policy School",
			code="ADMPOL",
			slug="admin-policy-school",
			email="policy@example.com",
			phone="+254700000023",
		)
		self.school_admin = User.objects.create_user(
			username="school.admin.policy",
			email="school.admin.policy@example.com",
			password="ChangeMe12345!",
			role=User.Role.SCHOOL_ADMIN,
			school=self.school,
		)
		self.superuser = User.objects.create_superuser(
			username="policy.superuser",
			email="policy.superuser@example.com",
			password="ChangeMe12345!",
		)

	def test_school_admin_cannot_access_django_admin(self):
		self.client.force_login(self.school_admin)
		response = self.client.get("/admin/")
		self.assertEqual(response.status_code, 302)
		self.assertIn("/admin/login/", response.url)

	def test_superuser_can_access_django_admin(self):
		self.client.force_login(self.superuser)
		response = self.client.get("/admin/")
		self.assertEqual(response.status_code, 200)


class AuditLogAccessTests(TestCase):
	def setUp(self):
		self.school = School.objects.create(
			name="Audit Policy School",
			code="AUDPOL",
			slug="audit-policy-school",
			email="audit-policy@example.com",
			phone="+254700000024",
		)
		self.school_admin = User.objects.create_user(
			username="audit.school.admin",
			email="audit.school.admin@example.com",
			password="ChangeMe12345!",
			role=User.Role.SCHOOL_ADMIN,
			school=self.school,
		)
		self.superuser = User.objects.create_superuser(
			username="audit.superuser",
			email="audit.superuser@example.com",
			password="ChangeMe12345!",
		)

	def test_school_admin_cannot_access_audit_log_list(self):
		self.client.force_login(self.school_admin)
		response = self.client.get(reverse("core:audit-log-list"))
		self.assertEqual(response.status_code, 403)

	def test_superuser_can_access_audit_log_list(self):
		self.client.force_login(self.superuser)
		response = self.client.get(reverse("core:audit-log-list"))
		self.assertEqual(response.status_code, 200)


class UserTeacherPermissionHelperTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.school = School.objects.create(
			name="Helper School",
			code="HELPER",
			slug="helper-school",
			email="helper@example.com",
			phone="+254700000030",
		)
		cls.other_school = School.objects.create(
			name="Other Helper School",
			code="OTHLP",
			slug="other-helper-school",
			email="other-helper@example.com",
			phone="+254700000031",
		)
		cls.year = AcademicYear.objects.create(
			school=cls.school,
			name="2026",
			start_date="2026-01-05",
			end_date="2026-11-20",
		)
		cls.other_year = AcademicYear.objects.create(
			school=cls.other_school,
			name="2026",
			start_date="2026-01-05",
			end_date="2026-11-20",
		)
		cls.section_a = ClassSection.objects.create(
			school=cls.school,
			academic_year=cls.year,
			grade_level="Grade 3",
			stream="A",
		)
		cls.section_b = ClassSection.objects.create(
			school=cls.school,
			academic_year=cls.year,
			grade_level="Grade 3",
			stream="B",
		)
		cls.other_section = ClassSection.objects.create(
			school=cls.other_school,
			academic_year=cls.other_year,
			grade_level="Grade 4",
			stream="A",
		)
		cls.math = Subject.objects.create(school=cls.school, name="Mathematics", code="MATH")
		cls.science = Subject.objects.create(school=cls.school, name="Science", code="SCI")
		cls.other_subject = Subject.objects.create(school=cls.other_school, name="Biology", code="BIO")

		cls.admin_user = User.objects.create_user(
			username="school.admin",
			password="ChangeMe12345!",
			role=User.Role.SCHOOL_ADMIN,
			school=cls.school,
		)
		cls.teacher_user = User.objects.create_user(
			username="teacher.helper",
			password="ChangeMe12345!",
			role=User.Role.TEACHER,
			school=cls.school,
		)
		cls.other_teacher_user = User.objects.create_user(
			username="teacher.other",
			password="ChangeMe12345!",
			role=User.Role.TEACHER,
			school=cls.other_school,
		)
		cls.superuser = User.objects.create_superuser(
			username="root",
			email="root@example.com",
			password="ChangeMe12345!",
		)

		cls.teacher_profile = Teacher.objects.create(
			school=cls.school,
			user=cls.teacher_user,
			employee_number="T-001",
		)
		cls.teacher_profile.assigned_classes.add(cls.section_a)
		cls.teacher_profile.assigned_subjects.add(cls.math)
		cls.teacher_profile.classes_in_charge.add(cls.section_a)

	def test_teacher_helpers_return_assigned_and_in_charge_classes(self):
		assigned_ids = set(self.teacher_user.get_assigned_classes().values_list("id", flat=True))
		in_charge_ids = set(self.teacher_user.get_classes_in_charge().values_list("id", flat=True))

		self.assertEqual(assigned_ids, {self.section_a.id})
		self.assertEqual(in_charge_ids, {self.section_a.id})

	def test_teacher_can_mark_only_owned_class_register(self):
		self.assertTrue(self.teacher_user.can_mark_class_register(self.section_a))
		self.assertFalse(self.teacher_user.can_mark_class_register(self.section_b))
		self.assertFalse(self.teacher_user.can_mark_class_register(self.other_section))

	def test_teacher_can_teach_only_assigned_subject_in_assigned_class(self):
		self.assertTrue(self.teacher_user.can_teach_subject_in_class(class_section=self.section_a, subject=self.math))
		self.assertFalse(self.teacher_user.can_teach_subject_in_class(class_section=self.section_a, subject=self.science))
		self.assertFalse(self.teacher_user.can_teach_subject_in_class(class_section=self.section_b, subject=self.math))
		self.assertFalse(self.teacher_user.can_teach_subject_in_class(class_section=self.other_section, subject=self.other_subject))

	def test_school_admin_gets_full_school_scope(self):
		assigned_ids = set(self.admin_user.get_assigned_classes().values_list("id", flat=True))
		self.assertEqual(assigned_ids, {self.section_a.id, self.section_b.id})
		self.assertTrue(self.admin_user.can_mark_class_register(self.section_b))

	def test_superuser_gets_global_scope(self):
		assigned_ids = set(self.superuser.get_assigned_classes().values_list("id", flat=True))
		self.assertEqual(assigned_ids, {self.section_a.id, self.section_b.id, self.other_section.id})
		self.assertTrue(self.superuser.can_mark_class_register(self.other_section))
