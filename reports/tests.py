import datetime
import json

from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassSection, GradeResult, Subject, Teacher, Term
from attendance.models import AttendanceStatus, DailyAttendance
from communication.models import Announcement
from core.models import AuditLog, School, User
from core.signals import sync_role_group_membership
from finance.models import FeeStructure, Invoice
from students.models import Enrollment, Student


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class ReportsBaseTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="KSMS Reports School",
            code="REPSCH",
            slug="ksms-reports-school",
            email="reports@testschool.example.com",
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
            grade_level="Form 1",
            stream="A",
            capacity=40,
        )

        cls.admin_user = User.objects.create_user(
            username="admin.reports",
            email="admin.reports@example.com",
            password="TestPass1234!",
            role=User.Role.SCHOOL_ADMIN,
            first_name="Admin",
            last_name="Reports",
        )
        sync_role_group_membership(cls.admin_user)

        cls.teacher_user = User.objects.create_user(
            username="teacher.reports",
            email="teacher.reports@example.com",
            password="TestPass1234!",
            role=User.Role.TEACHER,
            first_name="Teacher",
            last_name="Reports",
        )
        sync_role_group_membership(cls.teacher_user)

        cls.student_user = User.objects.create_user(
            username="student.reports",
            email="student.reports@example.com",
            password="TestPass1234!",
            role=User.Role.STUDENT,
        )
        sync_role_group_membership(cls.student_user)

        cls.student_user2 = User.objects.create_user(
            username="student2.reports",
            email="student2.reports@example.com",
            password="TestPass1234!",
            role=User.Role.STUDENT,
        )
        sync_role_group_membership(cls.student_user2)

        cls.parent_user = User.objects.create_user(
            username="parent.reports",
            email="parent.reports@example.com",
            password="TestPass1234!",
            role=User.Role.PARENT,
        )
        sync_role_group_membership(cls.parent_user)

        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="REP-001",
            admission_date=datetime.date(2026, 1, 9),
        )
        cls.student2 = Student.objects.create(
            school=cls.school,
            user=cls.student_user2,
            admission_number="REP-002",
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
        )
        cls.enrollment2 = Enrollment.objects.create(
            school=cls.school,
            student=cls.student2,
            academic_year=cls.academic_year,
            term=cls.term,
            class_section=cls.section,
            status=Enrollment.Status.ACTIVE,
            start_date=cls.term.start_date,
        )

        cls.subject = Subject.objects.create(
            school=cls.school,
            name="Mathematics",
            code="MATH01",
        )

        cls.fee_structure = FeeStructure.objects.create(
            school=cls.school,
            academic_year=cls.academic_year,
            term=cls.term,
            class_section=cls.section,
            name="Tuition",
            amount=5000,
            due_date=datetime.date(2026, 2, 1),
        )
        cls.invoice = Invoice.objects.create(
            enrollment=cls.enrollment,
            fee_structure=cls.fee_structure,
            amount_due=5000,
            amount_paid=0,
            status=Invoice.Status.PENDING,
        )

        cls.attendance = DailyAttendance.objects.create(
            enrollment=cls.enrollment,
            attendance_date=datetime.date(2026, 1, 10),
            status=AttendanceStatus.PRESENT,
            recorded_by=cls.teacher_user,
        )

        cls.grade = GradeResult.objects.create(
            enrollment=cls.enrollment,
            subject=cls.subject,
            score=78,
            grade="B",
        )


# ---------------------------------------------------------------------------
# Dashboard dispatch
# ---------------------------------------------------------------------------

class DashboardDispatchTests(ReportsBaseTestCase):

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertRedirects(response, f"/accounts/login/?next={reverse('core:dashboard')}", fetch_redirect_response=False)

    def test_admin_gets_admin_template(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/admin_dashboard.html')

    def test_teacher_gets_teacher_template(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/teacher_dashboard.html')

    def test_student_gets_student_template(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/student_dashboard.html')

    def test_parent_gets_parent_template(self):
        self.client.force_login(self.parent_user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/parent_dashboard.html')

    def test_superuser_gets_admin_template(self):
        superuser = User.objects.create_superuser(
            username="root.reports",
            email="root.reports@example.com",
            password="TestPass1234!",
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/admin_dashboard.html')


class DashboardSchoolScopeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Scope School A",
            code="SCPA",
            slug="scope-school-a",
            email="a@example.com",
            phone="+254700001001",
            county="Nairobi",
        )
        cls.school_b = School.objects.create(
            name="Scope School B",
            code="SCPB",
            slug="scope-school-b",
            email="b@example.com",
            phone="+254700001002",
            county="Nairobi",
        )

        cls.admin_a = User.objects.create_user(
            username="admin.scope.a",
            email="admin.scope.a@example.com",
            password="TestPass1234!",
            role=User.Role.SCHOOL_ADMIN,
            school=cls.school_a,
        )
        sync_role_group_membership(cls.admin_a)

        cls.admin_b = User.objects.create_user(
            username="admin.scope.b",
            email="admin.scope.b@example.com",
            password="TestPass1234!",
            role=User.Role.SCHOOL_ADMIN,
            school=cls.school_b,
        )
        sync_role_group_membership(cls.admin_b)

        cls.year_a = AcademicYear.objects.create(
            school=cls.school_a,
            name="2026",
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 11, 20),
            is_current=True,
        )
        cls.term_a = Term.objects.create(
            school=cls.school_a,
            academic_year=cls.year_a,
            name=Term.Name.TERM_1,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 4, 10),
            is_current=True,
        )
        cls.section_a = ClassSection.objects.create(
            school=cls.school_a,
            academic_year=cls.year_a,
            grade_level="Form 1",
            stream="A",
            capacity=40,
        )

        cls.year_b = AcademicYear.objects.create(
            school=cls.school_b,
            name="2026",
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 11, 20),
            is_current=True,
        )
        cls.term_b = Term.objects.create(
            school=cls.school_b,
            academic_year=cls.year_b,
            name=Term.Name.TERM_1,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 4, 10),
            is_current=True,
        )
        cls.section_b = ClassSection.objects.create(
            school=cls.school_b,
            academic_year=cls.year_b,
            grade_level="Form 1",
            stream="A",
            capacity=40,
        )

        cls.teacher_user_a = User.objects.create_user(
            username="teacher.scope.a",
            email="teacher.scope.a@example.com",
            password="TestPass1234!",
            role=User.Role.TEACHER,
            school=cls.school_a,
        )
        sync_role_group_membership(cls.teacher_user_a)
        cls.teacher_a = Teacher.objects.create(
            school=cls.school_a,
            user=cls.teacher_user_a,
            employee_number="TA-001",
        )

        cls.teacher_user_b = User.objects.create_user(
            username="teacher.scope.b",
            email="teacher.scope.b@example.com",
            password="TestPass1234!",
            role=User.Role.TEACHER,
            school=cls.school_b,
        )
        sync_role_group_membership(cls.teacher_user_b)
        cls.teacher_b = Teacher.objects.create(
            school=cls.school_b,
            user=cls.teacher_user_b,
            employee_number="TB-001",
        )

        cls.student_user_a = User.objects.create_user(
            username="student.scope.a",
            email="student.scope.a@example.com",
            password="TestPass1234!",
            role=User.Role.STUDENT,
            school=cls.school_a,
        )
        sync_role_group_membership(cls.student_user_a)
        cls.student_a = Student.objects.create(
            school=cls.school_a,
            user=cls.student_user_a,
            admission_number="SCA-001",
            admission_date=datetime.date(2026, 1, 7),
        )
        cls.enrollment_a = Enrollment.objects.create(
            school=cls.school_a,
            student=cls.student_a,
            academic_year=cls.year_a,
            term=cls.term_a,
            class_section=cls.section_a,
            status=Enrollment.Status.ACTIVE,
            start_date=cls.term_a.start_date,
        )

        cls.student_user_b = User.objects.create_user(
            username="student.scope.b",
            email="student.scope.b@example.com",
            password="TestPass1234!",
            role=User.Role.STUDENT,
            school=cls.school_b,
        )
        sync_role_group_membership(cls.student_user_b)
        cls.student_b = Student.objects.create(
            school=cls.school_b,
            user=cls.student_user_b,
            admission_number="SCB-001",
            admission_date=datetime.date(2026, 1, 7),
        )
        cls.enrollment_b = Enrollment.objects.create(
            school=cls.school_b,
            student=cls.student_b,
            academic_year=cls.year_b,
            term=cls.term_b,
            class_section=cls.section_b,
            status=Enrollment.Status.ACTIVE,
            start_date=cls.term_b.start_date,
        )

        today = datetime.date.today()
        DailyAttendance.objects.create(
            enrollment=cls.enrollment_a,
            attendance_date=today,
            status=AttendanceStatus.PRESENT,
            recorded_by=cls.teacher_user_a,
        )
        DailyAttendance.objects.create(
            enrollment=cls.enrollment_b,
            attendance_date=today,
            status=AttendanceStatus.ABSENT,
            recorded_by=cls.teacher_user_b,
        )

        subject_a = Subject.objects.create(school=cls.school_a, name="Math A", code="MATA")
        subject_b = Subject.objects.create(school=cls.school_b, name="Math B", code="MATB")

        fee_a = FeeStructure.objects.create(
            school=cls.school_a,
            academic_year=cls.year_a,
            term=cls.term_a,
            class_section=cls.section_a,
            name="Tuition",
            amount=5000,
            due_date=datetime.date(2026, 2, 1),
        )
        fee_b = FeeStructure.objects.create(
            school=cls.school_b,
            academic_year=cls.year_b,
            term=cls.term_b,
            class_section=cls.section_b,
            name="Tuition",
            amount=6000,
            due_date=datetime.date(2026, 2, 1),
        )
        Invoice.objects.create(
            enrollment=cls.enrollment_a,
            fee_structure=fee_a,
            amount_due=5000,
            amount_paid=0,
            status=Invoice.Status.PENDING,
        )
        Invoice.objects.create(
            enrollment=cls.enrollment_b,
            fee_structure=fee_b,
            amount_due=6000,
            amount_paid=0,
            status=Invoice.Status.PENDING,
        )

        GradeResult.objects.create(
            enrollment=cls.enrollment_a,
            subject=subject_a,
            score=70,
            grade="B",
        )
        GradeResult.objects.create(
            enrollment=cls.enrollment_b,
            subject=subject_b,
            score=65,
            grade="C",
        )

        AuditLog.objects.create(
            actor=cls.admin_a,
            action=AuditLog.Action.UPDATE,
            object_repr="Scoped entry A",
        )
        AuditLog.objects.create(
            actor=cls.admin_b,
            action=AuditLog.Action.UPDATE,
            object_repr="Scoped entry B",
        )

    def test_school_admin_dashboard_metrics_are_school_scoped(self):
        self.client.force_login(self.admin_a)
        response = self.client.get(reverse('core:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/admin_dashboard.html')
        self.assertEqual(response.context['student_count'], 1)
        self.assertEqual(response.context['teacher_count'], 1)
        self.assertEqual(response.context['today_total'], 1)
        self.assertEqual(response.context['invoice_pending'], 1)
        self.assertEqual(response.context['invoice_partial'], 0)
        self.assertEqual(response.context['invoice_paid'], 0)
        self.assertEqual(response.context['current_term'].school_id, self.school_a.id)

        self.assertEqual(list(response.context['recent_audit_logs']), [])

        chart_data = json.loads(response.context['chart_data'])
        self.assertEqual(chart_data['invoices']['values'], [1, 0, 0])


# ---------------------------------------------------------------------------
# Report access guards
# ---------------------------------------------------------------------------

class ReportAccessTests(ReportsBaseTestCase):

    ADMIN_TEACHER_URLS = [
        'reports:attendance',
        'reports:students',
        'reports:academics',
    ]
    ADMIN_ONLY_URLS = [
        'reports:fees',
    ]

    def _get(self, url_name, user):
        self.client.force_login(user)
        return self.client.get(reverse(url_name))

    def test_unauthenticated_attendance_redirects(self):
        response = self.client.get(reverse('reports:attendance'))
        self.assertIn(response.status_code, (302, 403))

    def test_admin_can_access_all_reports(self):
        for url_name in self.ADMIN_TEACHER_URLS + self.ADMIN_ONLY_URLS:
            with self.subTest(url=url_name):
                response = self._get(url_name, self.admin_user)
                self.assertEqual(response.status_code, 200)

    def test_teacher_can_access_admin_teacher_reports(self):
        for url_name in self.ADMIN_TEACHER_URLS:
            with self.subTest(url=url_name):
                response = self._get(url_name, self.teacher_user)
                self.assertEqual(response.status_code, 200)

    def test_teacher_blocked_from_fee_report(self):
        response = self._get('reports:fees', self.teacher_user)
        self.assertIn(response.status_code, (302, 403))

    def test_student_blocked_from_attendance_report(self):
        response = self._get('reports:attendance', self.student_user)
        self.assertIn(response.status_code, (302, 403))

    def test_parent_blocked_from_attendance_report(self):
        response = self._get('reports:attendance', self.parent_user)
        self.assertIn(response.status_code, (302, 403))


# ---------------------------------------------------------------------------
# CSV export tests
# ---------------------------------------------------------------------------

class CSVExportTests(ReportsBaseTestCase):

    def test_attendance_csv_returns_csv_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:attendance-csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_attendance_csv_contains_header_row(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:attendance-csv'))
        content = response.content.decode('utf-8')
        self.assertIn('Date', content)
        self.assertIn('Student', content)

    def test_attendance_csv_respects_query_filter(self):
        DailyAttendance.objects.create(
            enrollment=self.enrollment2,
            attendance_date=datetime.date(2026, 1, 11),
            status=AttendanceStatus.ABSENT,
            recorded_by=self.teacher_user,
        )
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:attendance-csv'), {'q': 'REP-001'})
        content = response.content.decode('utf-8')
        self.assertIn('REP-001', content)
        self.assertNotIn('REP-002', content)

    def test_fees_csv_returns_csv_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:fees-csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_students_csv_returns_csv_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:students-csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_academics_csv_returns_csv_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:academics-csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_fees_csv_blocked_for_teacher(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('reports:fees-csv'))
        self.assertIn(response.status_code, (302, 403))


class PDFExportTests(ReportsBaseTestCase):

    def test_attendance_pdf_returns_pdf_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:attendance-pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])

    def test_fees_pdf_returns_pdf_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:fees-pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])

    def test_students_pdf_returns_pdf_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:students-pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])

    def test_academics_pdf_returns_pdf_content_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports:academics-pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])

    def test_fees_pdf_blocked_for_teacher(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('reports:fees-pdf'))
        self.assertIn(response.status_code, (302, 403))

    def test_pdf_export_creates_audit_log_entry(self):
        self.client.force_login(self.admin_user)
        self.client.get(reverse('reports:attendance-pdf'))
        entry = AuditLog.objects.filter(metadata__event='report_export').first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.metadata.get('report'), 'attendance')
        self.assertEqual(entry.metadata.get('format'), 'pdf')


# ---------------------------------------------------------------------------
# Report card access
# ---------------------------------------------------------------------------

class ReportCardTests(ReportsBaseTestCase):

    def _url(self, student):
        return reverse('reports:report-card', kwargs={'pk': student.pk})

    def test_admin_can_view_any_report_card(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self._url(self.student))
        self.assertEqual(response.status_code, 200)

    def test_teacher_can_view_any_report_card(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(self._url(self.student))
        self.assertEqual(response.status_code, 200)

    def test_student_can_view_own_report_card(self):
        self.client.force_login(self.student_user)
        response = self.client.get(self._url(self.student))
        self.assertEqual(response.status_code, 200)

    def test_student_blocked_from_other_student_report_card(self):
        self.client.force_login(self.student_user)
        response = self.client.get(self._url(self.student2))
        self.assertEqual(response.status_code, 403)

    def test_parent_blocked_from_report_card(self):
        self.client.force_login(self.parent_user)
        response = self.client.get(self._url(self.student))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirects(self):
        response = self.client.get(self._url(self.student))
        self.assertIn(response.status_code, (302, 403))

    def test_report_card_contains_student_name(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self._url(self.student))
        self.assertContains(response, self.student.admission_number)


# ---------------------------------------------------------------------------
# Announcement model
# ---------------------------------------------------------------------------

class AnnouncementModelTests(ReportsBaseTestCase):

    def setUp(self):
        Announcement.objects.create(
            school=self.school,
            title="All students notice",
            body="Please attend assembly.",
            audience=Announcement.Audience.ALL,
            is_active=True,
            author=self.admin_user,
        )
        Announcement.objects.create(
            school=self.school,
            title="Parents only notice",
            body="Fee deadline reminder.",
            audience=Announcement.Audience.PARENTS,
            is_active=True,
            author=self.admin_user,
        )
        Announcement.objects.create(
            school=self.school,
            title="Inactive notice",
            body="Should not appear.",
            audience=Announcement.Audience.ALL,
            is_active=False,
            author=self.admin_user,
        )

    def test_active_filter(self):
        qs = Announcement.objects.filter(school=self.school, is_active=True)
        self.assertEqual(qs.count(), 2)

    def test_audience_filter_all(self):
        qs = Announcement.objects.filter(
            school=self.school,
            is_active=True,
            audience__in=[Announcement.Audience.ALL, Announcement.Audience.STUDENTS],
        )
        self.assertEqual(qs.count(), 1)

    def test_audience_filter_parents(self):
        qs = Announcement.objects.filter(
            school=self.school,
            is_active=True,
            audience__in=[Announcement.Audience.ALL, Announcement.Audience.PARENTS],
        )
        self.assertEqual(qs.count(), 2)

    def test_str_representation(self):
        ann = Announcement.objects.filter(school=self.school, is_active=True).first()
        self.assertIn(ann.title, str(ann))
