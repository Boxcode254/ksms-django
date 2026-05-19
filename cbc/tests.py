"""Tests for the CBC report card module.

Mirrors the discipline used in :mod:`finance.tests` — a single shared
``setUpTestData`` fixture for the bulk of cases, plus targeted classes
for permissions, model invariants, and PDF rendering.
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassSection, Subject, Term
from attendance.models import AttendanceStatus, DailyAttendance
from cbc.models import (
    CBCAssessment,
    CBCCoreCompetency,
    CBCLevel,
    CBCReport,
    CoreCompetency,
    Strand,
    SubStrand,
)
from cbc.services.grading import level_from_score
from core.models import School, User
from core.signals import sync_role_group_membership
from students.models import (
    Enrollment,
    Guardian,
    Student,
    StudentGuardianRelationship,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

class CBCBaseTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="KSMS CBC School",
            code="CBCSCH",
            slug="ksms-cbc-school",
            email="cbc@example.com",
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
        cls.section = ClassSection.objects.create(
            school=cls.school,
            academic_year=cls.academic_year,
            grade_level="Grade 4",
            stream="A",
            capacity=40,
        )

        # Users
        cls.admin_user = User.objects.create_user(
            username="admin.cbc", email="admin.cbc@example.com",
            password="TestPass1234", role=User.Role.SCHOOL_ADMIN,
            first_name="CBC", last_name="Admin",
        )
        sync_role_group_membership(cls.admin_user)
        cls.teacher_user = User.objects.create_user(
            username="teacher.cbc", email="teacher.cbc@example.com",
            password="TestPass1234", role=User.Role.TEACHER,
        )
        sync_role_group_membership(cls.teacher_user)
        cls.student_user = User.objects.create_user(
            username="student.cbc", email="student.cbc@example.com",
            password="TestPass1234", role=User.Role.STUDENT,
        )
        sync_role_group_membership(cls.student_user)
        cls.other_student_user = User.objects.create_user(
            username="other.student.cbc", email="other.student.cbc@example.com",
            password="TestPass1234", role=User.Role.STUDENT,
        )
        sync_role_group_membership(cls.other_student_user)
        cls.parent_user = User.objects.create_user(
            username="parent.cbc", email="parent.cbc@example.com",
            password="TestPass1234", role=User.Role.PARENT,
        )
        sync_role_group_membership(cls.parent_user)
        cls.other_parent_user = User.objects.create_user(
            username="other.parent.cbc", email="other.parent.cbc@example.com",
            password="TestPass1234", role=User.Role.PARENT,
        )
        sync_role_group_membership(cls.other_parent_user)

        cls.student = Student.objects.create(
            school=cls.school, user=cls.student_user,
            admission_number="CBC-001",
            admission_date=datetime.date(2026, 1, 9),
        )
        cls.other_student = Student.objects.create(
            school=cls.school, user=cls.other_student_user,
            admission_number="CBC-002",
            admission_date=datetime.date(2026, 1, 9),
        )
        cls.guardian = Guardian.objects.create(school=cls.school, user=cls.parent_user)
        cls.other_guardian = Guardian.objects.create(school=cls.school, user=cls.other_parent_user)
        StudentGuardianRelationship.objects.create(
            student=cls.student,
            guardian=cls.guardian,
            relationship=StudentGuardianRelationship.Relationship.MOTHER,
            is_primary_contact=True,
        )
        StudentGuardianRelationship.objects.create(
            student=cls.other_student,
            guardian=cls.other_guardian,
            relationship=StudentGuardianRelationship.Relationship.MOTHER,
            is_primary_contact=True,
        )

        cls.enrollment = Enrollment.objects.create(
            school=cls.school, student=cls.student,
            academic_year=cls.academic_year, term=cls.term,
            class_section=cls.section, status=Enrollment.Status.ACTIVE,
            start_date=cls.term.start_date,
        )
        cls.other_enrollment = Enrollment.objects.create(
            school=cls.school, student=cls.other_student,
            academic_year=cls.academic_year, term=cls.term,
            class_section=cls.section, status=Enrollment.Status.ACTIVE,
            start_date=cls.term.start_date,
        )

        cls.subject = Subject.objects.create(
            school=cls.school, name="Mathematics", code="MATH",
        )
        cls.strand = Strand.objects.create(
            subject=cls.subject, grade_level="Grade 4", name="Numbers", order=1,
        )
        cls.sub_strand = SubStrand.objects.create(
            strand=cls.strand, name="Whole numbers", order=1,
        )

        cls.report = CBCReport.objects.create(
            enrollment=cls.enrollment, term=cls.term,
        )
        cls.other_report = CBCReport.objects.create(
            enrollment=cls.other_enrollment, term=cls.term,
        )

    def login(self, user):
        self.client.force_login(user)


# ---------------------------------------------------------------------------
# Score → level conversion
# ---------------------------------------------------------------------------

class GradingTests(TestCase):

    def test_level_boundaries(self):
        cases = {
            0: "BE", 1: "BE", 39: "BE",
            40: "AE", 41: "AE", 59: "AE",
            60: "ME", 61: "ME", 79: "ME",
            80: "EE", 100: "EE",
        }
        for score, expected in cases.items():
            with self.subTest(score=score):
                self.assertEqual(level_from_score(score), expected)

    def test_decimal_input_supported(self):
        self.assertEqual(level_from_score(Decimal("59.99")), "AE")
        self.assertEqual(level_from_score(Decimal("60.00")), "ME")

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            level_from_score(-1)
        with self.assertRaises(ValueError):
            level_from_score(101)

    def test_none_score_raises(self):
        with self.assertRaises(ValueError):
            level_from_score(None)


# ---------------------------------------------------------------------------
# Model invariants
# ---------------------------------------------------------------------------

class CBCModelTests(CBCBaseTestCase):

    def test_assessment_save_derives_level(self):
        assessment = CBCAssessment.objects.create(
            report=self.report,
            subject=self.subject,
            strand=self.strand,
            sub_strand=self.sub_strand,
            score=Decimal("75"),
        )
        self.assertEqual(assessment.level, "ME")

        assessment.score = Decimal("82")
        assessment.save()
        assessment.refresh_from_db()
        self.assertEqual(assessment.level, "EE")

    def test_assessment_unique_per_subject_strand_sub_strand(self):
        CBCAssessment.objects.create(
            report=self.report, subject=self.subject,
            strand=self.strand, sub_strand=self.sub_strand,
            score=Decimal("70"),
        )
        with self.assertRaises(Exception):
            CBCAssessment.objects.create(
                report=self.report, subject=self.subject,
                strand=self.strand, sub_strand=self.sub_strand,
                score=Decimal("80"),
            )

    def test_report_unique_per_enrollment_term(self):
        with self.assertRaises(Exception):
            CBCReport.objects.create(enrollment=self.enrollment, term=self.term)

    def test_attendance_snapshot(self):
        DailyAttendance.objects.bulk_create([
            DailyAttendance(enrollment=self.enrollment,
                            attendance_date=self.term.start_date + datetime.timedelta(days=i),
                            status=AttendanceStatus.PRESENT)
            for i in range(8)
        ])
        DailyAttendance.objects.create(
            enrollment=self.enrollment,
            attendance_date=self.term.start_date + datetime.timedelta(days=8),
            status=AttendanceStatus.ABSENT,
        )
        # Out-of-range row should not be counted
        DailyAttendance.objects.create(
            enrollment=self.enrollment,
            attendance_date=self.term.end_date + datetime.timedelta(days=5),
            status=AttendanceStatus.PRESENT,
        )

        self.report.snapshot_attendance()
        self.assertEqual(self.report.total_school_days, 9)
        self.assertEqual(self.report.days_present, 8)

    def test_overall_level_uses_average(self):
        CBCAssessment.objects.create(
            report=self.report, subject=self.subject,
            strand=self.strand, sub_strand=self.sub_strand,
            score=Decimal("85"),
        )
        # Different sub-strand to avoid the unique constraint
        sub2 = SubStrand.objects.create(strand=self.strand, name="Fractions", order=2)
        CBCAssessment.objects.create(
            report=self.report, subject=self.subject,
            strand=self.strand, sub_strand=sub2,
            score=Decimal("75"),
        )
        self.assertEqual(self.report.overall_level, "EE")


# ---------------------------------------------------------------------------
# Permissions on the CBC views
# ---------------------------------------------------------------------------

class CBCPermissionTests(CBCBaseTestCase):

    def test_report_list_requires_login(self):
        response = self.client.get(reverse("cbc:report-list"))
        self.assertEqual(response.status_code, 302)

    def test_admin_can_access_report_list(self):
        self.login(self.admin_user)
        self.assertEqual(self.client.get(reverse("cbc:report-list")).status_code, 200)

    def test_teacher_can_access_report_list(self):
        self.login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("cbc:report-list")).status_code, 200)

    def test_parent_blocked_from_report_list(self):
        self.login(self.parent_user)
        self.assertEqual(self.client.get(reverse("cbc:report-list")).status_code, 403)

    def test_student_blocked_from_report_list(self):
        self.login(self.student_user)
        self.assertEqual(self.client.get(reverse("cbc:report-list")).status_code, 403)

    def test_admin_can_view_any_report_detail(self):
        self.login(self.admin_user)
        url = reverse("cbc:report-detail", args=[self.report.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_student_can_view_own_report(self):
        self.student_user.student_profile  # touch reverse accessor
        self.login(self.student_user)
        url = reverse("cbc:report-detail", args=[self.report.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_student_blocked_from_other_student_report(self):
        self.login(self.student_user)
        url = reverse("cbc:report-detail", args=[self.other_report.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_parent_can_view_ward_report(self):
        self.login(self.parent_user)
        url = reverse("cbc:report-detail", args=[self.report.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_parent_blocked_from_other_ward_report(self):
        self.login(self.parent_user)
        url = reverse("cbc:report-detail", args=[self.other_report.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_strand_create_admin_only(self):
        self.login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("cbc:strand-create")).status_code, 403)
        self.login(self.admin_user)
        self.assertEqual(self.client.get(reverse("cbc:strand-create")).status_code, 200)


# ---------------------------------------------------------------------------
# Report create / edit flow
# ---------------------------------------------------------------------------

class CBCReportFlowTests(CBCBaseTestCase):

    def test_create_report_redirects_to_edit(self):
        # Use a fresh enrollment so the unique constraint does not collide.
        new_term = Term.objects.create(
            school=self.school, academic_year=self.academic_year,
            name=Term.Name.TERM_2,
            start_date=datetime.date(2026, 5, 1),
            end_date=datetime.date(2026, 8, 1),
        )
        new_enrollment = Enrollment.objects.create(
            school=self.school, student=self.student,
            academic_year=self.academic_year, term=new_term,
            class_section=self.section, status=Enrollment.Status.ACTIVE,
            start_date=new_term.start_date,
        )
        self.login(self.admin_user)
        response = self.client.post(
            reverse("cbc:report-create"),
            {"enrollment": new_enrollment.pk},
        )
        self.assertEqual(response.status_code, 302)
        new_report = CBCReport.objects.get(enrollment=new_enrollment)
        self.assertRedirects(response, reverse("cbc:report-edit", args=[new_report.pk]))
        self.assertEqual(new_report.term_id, new_term.pk)
        self.assertEqual(new_report.generated_by, self.admin_user)

    def test_duplicate_report_rejected(self):
        # cls.report already exists for (self.enrollment, self.term)
        self.login(self.admin_user)
        response = self.client.post(
            reverse("cbc:report-create"),
            {"enrollment": self.enrollment.pk},
        )
        self.assertEqual(response.status_code, 200)  # form re-renders with error
        self.assertContains(response, "already exists")

    def test_edit_view_seeds_seven_core_competencies(self):
        self.login(self.teacher_user)
        self.assertEqual(self.report.core_competencies.count(), 0)
        response = self.client.get(reverse("cbc:report-edit", args=[self.report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.report.core_competencies.count(), len(CoreCompetency.choices)
        )

    def test_edit_view_bootstraps_assessment_rows_from_catalog(self):
        self.login(self.teacher_user)
        self.assertEqual(self.report.assessments.count(), 0)
        response = self.client.get(reverse("cbc:report-edit", args=[self.report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.report.assessments.count(), 1)
        assessment = self.report.assessments.get()
        self.assertEqual(assessment.subject, self.subject)
        self.assertEqual(assessment.strand, self.strand)
        self.assertEqual(assessment.sub_strand, self.sub_strand)
        self.assertEqual(assessment.level, CBCLevel.BE)

    def test_refresh_attendance_updates_snapshot(self):
        DailyAttendance.objects.create(
            enrollment=self.enrollment,
            attendance_date=self.term.start_date,
            status=AttendanceStatus.PRESENT,
        )
        self.login(self.teacher_user)
        response = self.client.post(reverse("cbc:report-refresh-attendance", args=[self.report.pk]))
        self.assertEqual(response.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.total_school_days, 1)
        self.assertEqual(self.report.days_present, 1)


# ---------------------------------------------------------------------------
# PDF rendering (mock weasyprint to avoid system deps in CI)
# ---------------------------------------------------------------------------

class CBCPDFTests(CBCBaseTestCase):

    @patch("cbc.services.pdf.HTML", create=True)
    def _patched_get(self, mock_html, url, *, login_as):
        # The lazy import inside ``render_report_pdf_bytes`` looks up
        # ``HTML`` via ``from weasyprint import HTML``; patch the local
        # binding inside :mod:`cbc.services.pdf` to bypass real PDF gen.
        mock_html.return_value.write_pdf.return_value = b"%PDF-FAKE"
        self.login(login_as)
        return self.client.get(url)

    def test_admin_pdf_response_type(self):
        with patch("cbc.views.render_report_pdf", return_value=b"%PDF-FAKE"):
            self.login(self.admin_user)
            response = self.client.get(
                reverse("cbc:report-pdf", args=[self.report.pk])
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(self.student.admission_number, response["Content-Disposition"])

    def test_parent_pdf_inline_disposition(self):
        with patch("cbc.views.render_report_pdf", return_value=b"%PDF-FAKE"):
            self.login(self.parent_user)
            response = self.client.get(
                reverse("cbc:report-pdf", args=[self.report.pk])
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("inline", response["Content-Disposition"])

    def test_other_parent_blocked_from_pdf(self):
        with patch("cbc.views.render_report_pdf", return_value=b"%PDF-FAKE"):
            self.login(self.other_parent_user)
            response = self.client.get(
                reverse("cbc:report-pdf", args=[self.report.pk])
            )
        self.assertEqual(response.status_code, 403)

    def test_pdf_service_calls_weasyprint_with_rendered_html(self):
        with patch("weasyprint.HTML") as mock_html:
            mock_html.return_value.write_pdf.return_value = b"%PDF-FAKE"
            from cbc.services.pdf import render_report_pdf

            pdf = render_report_pdf(self.report, base_url="http://testserver/")

        self.assertEqual(pdf, b"%PDF-FAKE")
        self.assertTrue(mock_html.called)
        self.assertIn(self.student.admission_number, mock_html.call_args.kwargs["string"])

    def test_student_history_canonical_url_resolves(self):
        self.login(self.parent_user)
        response = self.client.get(reverse("cbc:student-history", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Strand catalog smoke
# ---------------------------------------------------------------------------

class StrandCatalogTests(CBCBaseTestCase):

    def test_strand_list_visible_to_staff(self):
        self.login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("cbc:strand-list")).status_code, 200)

    def test_strand_create_persists(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("cbc:strand-create"),
            {
                "subject": self.subject.pk,
                "grade_level": "Grade 4",
                "name": "Algebra",
                "code": "",
                "order": 2,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Strand.objects.filter(
                subject=self.subject, grade_level="Grade 4", name="Algebra"
            ).exists()
        )
