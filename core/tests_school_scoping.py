"""School (tenant) scoping tests for staff queries — task t_d062a79e.

Two identical school trees are built (Alpha Academy = A, Beta School = B).
Every cross-school case logs in as school A's admin and asserts that
school B's rows are invisible (lists/exports) or 404 (single-object),
and that a ``school=None`` superuser still sees both schools.

RED phase history: written against the pre-mixin code, where the
cross-school cases failed (B rows visible in lists/exports, ``200 != 404``
on B objects' update/delete URLs; RED run: ``FAILED (failures=64,
errors=6, skipped=6)``). Two pre-existing conditions surfaced by the RED
run, both outside this card's scoping mechanism:
* the role mixins 403 the SUPERUSER role on all 29 views (superuser
  coverage therefore lives at the queryset layer, see
  ``PerViewQuerysetScopingTests.test_superuser_sees_both_schools_in_every_scoped_queryset``);
* ``finance:payment-deleted-list`` returned 500 for everyone —
  ``Payment.all_objects.deleted()``: AllSoftDeleteManager has no
  ``deleted()`` shortcut (fixed inline in the view as part of scoping it).

Harness: ``docker exec -e DEBUG=1 <container> python manage.py test core.tests_school_scoping --noinput``
(DEBUG=1 disables SECURE_SSL_REDIRECT, which otherwise 301s every
request in the prod container).
"""
import base64
import datetime
import re
import unittest
import zlib
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views.generic import ListView

from academics.models import (
    AcademicYear,
    ClassSection,
    GradeResult,
    Subject,
    Term,
    Teacher,
    TeachingAssignment,
    TimetableEntry,
)
from academics.views import (
    ClassSectionUpdateView,
    GradeResultUpdateView,
    SubjectUpdateView,
    TeacherUpdateView,
    TimetableEntryUpdateView,
)
from attendance.models import AttendanceStatus, DailyAttendance, PeriodAttendance
from attendance.views import DailyAttendanceUpdateView, PeriodAttendanceUpdateView
from cbc.models import CBCReport, Strand, SubStrand
from cbc.views import (
    CBCReportListView,
    StrandDeleteView,
    StrandListView,
    StrandUpdateView,
    SubStrandDeleteView,
    SubStrandUpdateView,
)
from core.models import School, User
from core.signals import sync_role_group_membership
from finance.models import FeeStructure, Invoice, Payment
from finance.views import DeletedPaymentListView, FeeStructureUpdateView, InvoiceUpdateView
from reports.views import (
    AcademicSummaryCSVView,
    AcademicSummaryPDFView,
    AttendanceReportCSVView,
    AttendanceReportPDFView,
    FeeReportCSVView,
    FeeReportPDFView,
    StudentRegisterCSVView,
    StudentRegisterPDFView,
)
from students.models import (
    Enrollment,
    Guardian,
    Student,
    StudentGuardianRelationship,
)
from students.views import (
    EnrollmentUpdateView,
    GuardianUpdateView,
    StudentGuardianRelationshipDeleteView,
    StudentGuardianRelationshipUpdateView,
    StudentUpdateView,
)

try:  # mixin under test — absent during the RED phase
    from core.school_scoping import SchoolScopedQuerysetMixin
except ImportError:
    SchoolScopedQuerysetMixin = None


PASSWORD = "TestPass1234"
A_STUDENT_ADM_NO = "SCA-001"
B_STUDENT_ADM_NO = "SCB-001"

# ---------------------------------------------------------------------------
# Per-view scoping table: every class named on the task card (3 + 26 = 29).
# (view class, model, fixture attr holding an A object / a B object)
# ---------------------------------------------------------------------------
SCOPED_VIEW_TABLE = (
    # List A — queryset defined but unscoped
    (CBCReportListView, CBCReport, "report"),
    (StrandListView, Strand, "strand"),
    (DeletedPaymentListView, Payment, "deleted_payment"),
    # List B — no get_queryset at all
    (ClassSectionUpdateView, ClassSection, "section"),
    (SubjectUpdateView, Subject, "subject"),
    (TimetableEntryUpdateView, TimetableEntry, "timetable"),
    (GradeResultUpdateView, GradeResult, "grade"),
    (TeacherUpdateView, Teacher, "teacher"),
    (DailyAttendanceUpdateView, DailyAttendance, "daily"),
    (PeriodAttendanceUpdateView, PeriodAttendance, "period"),
    (StrandUpdateView, Strand, "strand"),
    (StrandDeleteView, Strand, "strand"),
    (SubStrandUpdateView, SubStrand, "substrand"),
    (SubStrandDeleteView, SubStrand, "substrand"),
    (FeeStructureUpdateView, FeeStructure, "fee_structure"),
    (InvoiceUpdateView, Invoice, "invoice"),
    (AttendanceReportCSVView, DailyAttendance, "daily"),
    (AttendanceReportPDFView, DailyAttendance, "daily"),
    (FeeReportCSVView, Invoice, "invoice"),
    (FeeReportPDFView, Invoice, "invoice"),
    (StudentRegisterCSVView, Enrollment, "enrollment"),
    (StudentRegisterPDFView, Enrollment, "enrollment"),
    (AcademicSummaryCSVView, GradeResult, "grade"),
    (AcademicSummaryPDFView, GradeResult, "grade"),
    (StudentUpdateView, Student, "student"),
    (GuardianUpdateView, Guardian, "guardian"),
    (StudentGuardianRelationshipUpdateView, StudentGuardianRelationship, "relationship"),
    (StudentGuardianRelationshipDeleteView, StudentGuardianRelationship, "relationship"),
    (EnrollmentUpdateView, Enrollment, "enrollment"),
)

# Update/delete URLs: (url name, fixture attr, action)
UPDATE_DELETE_URL_CASES = (
    ("academics:classsection-update", "section", "update"),
    ("academics:subject-update", "subject", "update"),
    ("academics:timetable-update", "timetable", "update"),
    ("academics:grade-update", "grade", "update"),
    ("academics:teacher-update", "teacher", "update"),
    ("attendance:daily-update", "daily", "update"),
    ("attendance:period-update", "period", "update"),
    ("cbc:strand-edit", "strand", "update"),
    ("cbc:strand-delete", "strand", "delete"),
    ("cbc:sub-strand-edit", "substrand", "update"),
    ("cbc:sub-strand-delete", "substrand", "delete"),
    ("finance:feestructure-update", "fee_structure", "update"),
    ("finance:invoice-update", "invoice", "update"),
    ("students:student-update", "student", "update"),
    ("students:guardian-update", "guardian", "update"),
    ("students:relationship-update", "relationship", "update"),
    ("students:relationship-delete", "relationship", "delete"),
    ("students:enrollment-update", "enrollment", "update"),
)

# Export endpoints of the reports module: (url name, is_pdf)
REPORT_EXPORT_CASES = (
    ("reports:attendance-csv", False),
    ("reports:attendance-pdf", True),
    ("reports:fees-csv", False),
    ("reports:fees-pdf", True),
    ("reports:students-csv", False),
    ("reports:students-pdf", True),
    ("reports:academics-csv", False),
    ("reports:academics-pdf", True),
)

# List endpoints on the card: (url name, context var, fixture attr)
LIST_CASES = (
    ("cbc:report-list", "reports", "report"),
    ("cbc:strand-list", "strands", "strand"),
    ("finance:payment-deleted-list", "payments", "payment"),
)


def _pdf_text(content):
    """Extract text from reportlab PDF bytes.

    reportlab encodes content streams with ASCII85 (rl_config.useA85) and
    optional Flate compression; decode a85 then zlib, best effort per stream.
    """
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", content, re.DOTALL):
        data = match.group(1).rstrip()
        try:
            data = base64.a85decode(data, adobe=True)
        except Exception:
            pass
        try:
            data = zlib.decompress(data)
        except zlib.error:
            pass
        chunks.append(data.decode("latin-1", "replace"))
    return "\n".join(chunks)


class TwoSchoolTestCase(TestCase):
    """School A + School B with identical staff/student/finance trees."""

    @classmethod
    def setUpTestData(cls):
        cls.rf = RequestFactory()
        cls.school_a = School.objects.create(
            name="Alpha Academy",
            code="ALPHA",
            slug="alpha-academy",
            email="alpha@example.com",
            phone="+254700000001",
            county="Nairobi",
        )
        cls.school_b = School.objects.create(
            name="Beta School",
            code="BETA",
            slug="beta-school",
            email="beta@example.com",
            phone="+254700000002",
            county="Nairobi",
        )
        cls.a = cls._build_school_tree("a", cls.school_a)
        cls.b = cls._build_school_tree("b", cls.school_b)

        cls.superuser = User.objects.create_superuser(
            username="root.scope",
            email="root.scope@example.com",
            password=PASSWORD,
        )
        sync_role_group_membership(cls.superuser)

    @classmethod
    def _build_school_tree(cls, tag, school):
        code = tag.upper()
        t = SimpleNamespace()
        t.school = school
        t.year = AcademicYear.objects.create(
            school=school,
            name="2026",
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 11, 20),
            is_current=True,
        )
        t.term = Term.objects.create(
            school=school,
            academic_year=t.year,
            name=Term.Name.TERM_1,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 4, 10),
            is_current=True,
        )
        t.section = ClassSection.objects.create(
            school=school,
            academic_year=t.year,
            grade_level="Form 1",
            stream="A",
            capacity=40,
            room_name=f"Room-{code}",
        )
        t.subject = Subject.objects.create(
            school=school,
            name="Mathematics",
            code=f"MAT-{code}",
        )
        t.admin = User.objects.create_user(
            username=f"admin.{tag}",
            email=f"admin.{tag}@example.com",
            password=PASSWORD,
            role=User.Role.SCHOOL_ADMIN,
            school=school,
            first_name=f"Admin{code}",
            last_name="User",
        )
        sync_role_group_membership(t.admin)
        t.teacher_user = User.objects.create_user(
            username=f"teacher.{tag}",
            email=f"teacher.{tag}@example.com",
            password=PASSWORD,
            role=User.Role.TEACHER,
            school=school,
        )
        sync_role_group_membership(t.teacher_user)
        t.teacher = Teacher.objects.create(
            school=school,
            user=t.teacher_user,
            employee_number=f"EMP-{code}1",
        )
        t.student_user = User.objects.create_user(
            username=f"student.{tag}",
            email=f"student.{tag}@example.com",
            password=PASSWORD,
            role=User.Role.STUDENT,
            school=school,
        )
        sync_role_group_membership(t.student_user)
        t.student = Student.objects.create(
            school=school,
            user=t.student_user,
            admission_number=f"SC{code}-001",
            admission_date=datetime.date(2026, 1, 9),
        )
        t.parent_user = User.objects.create_user(
            username=f"parent.{tag}",
            email=f"parent.{tag}@example.com",
            password=PASSWORD,
            role=User.Role.PARENT,
            school=school,
        )
        sync_role_group_membership(t.parent_user)
        t.guardian = Guardian.objects.create(school=school, user=t.parent_user)
        t.relationship = StudentGuardianRelationship.objects.create(
            student=t.student,
            guardian=t.guardian,
            relationship=StudentGuardianRelationship.Relationship.MOTHER,
            is_primary_contact=True,
        )
        t.enrollment = Enrollment.objects.create(
            school=school,
            student=t.student,
            academic_year=t.year,
            term=t.term,
            class_section=t.section,
            status=Enrollment.Status.ACTIVE,
            start_date=t.term.start_date,
        )
        t.fee_structure = FeeStructure.objects.create(
            school=school,
            academic_year=t.year,
            term=t.term,
            class_section=t.section,
            name="Tuition Fee",
            amount=Decimal("15000.00"),
            due_date=datetime.date(2026, 2, 1),
            is_active=True,
        )
        t.invoice = Invoice.objects.create(
            enrollment=t.enrollment,
            fee_structure=t.fee_structure,
            amount_due=Decimal("15000.00"),
            due_date=datetime.date(2026, 2, 1),
            status=Invoice.Status.PENDING,
        )
        t.payment = Payment.objects.create(
            invoice=t.invoice,
            amount=Decimal("1500.00"),
            payment_method=Payment.Method.CASH,
            status=Payment.Status.SUCCESSFUL,
            received_by=t.admin,
        )
        t.daily = DailyAttendance.objects.create(
            enrollment=t.enrollment,
            attendance_date=datetime.date(2026, 2, 2),
            status=AttendanceStatus.PRESENT,
            recorded_by=t.admin,
        )
        t.period = PeriodAttendance.objects.create(
            enrollment=t.enrollment,
            subject=t.subject,
            period_number=1,
            attendance_date=datetime.date(2026, 2, 2),
            status=AttendanceStatus.PRESENT,
            recorded_by=t.admin,
        )
        t.grade = GradeResult.objects.create(
            enrollment=t.enrollment,
            subject=t.subject,
            exam_type=GradeResult.ExamType.CAT,
            score=Decimal("80.00"),
            recorded_by=t.teacher_user,
        )
        t.assignment = TeachingAssignment.objects.create(
            school=school,
            class_section=t.section,
            subject=t.subject,
            teacher=t.teacher,
        )
        t.timetable = TimetableEntry.objects.create(
            school=school,
            term=t.term,
            teaching_assignment=t.assignment,
            weekday=1,
            start_time=datetime.time(8, 0),
            end_time=datetime.time(9, 0),
        )
        t.strand = Strand.objects.create(
            subject=t.subject,
            grade_level="Form 1",
            name="Numbers",
            order=1,
        )
        t.substrand = SubStrand.objects.create(strand=t.strand, name="Counting", order=1)
        t.report = CBCReport.objects.create(
            enrollment=t.enrollment,
            term=t.term,
            generated_by=t.admin,
        )
        # A soft-deleted payment per school — the only rows the deleted
        # payments list ever shows.
        t.deleted_payment = Payment.objects.create(
            invoice=t.invoice,
            amount=Decimal("200.00"),
            payment_method=Payment.Method.CASH,
            status=Payment.Status.SUCCESSFUL,
            received_by=t.admin,
        )
        t.deleted_payment.delete()
        return t

    def login(self, user):
        self.client.force_login(user)


# ---------------------------------------------------------------------------
# Required case 1 + 4 — list scoping and the superuser bypass
# ---------------------------------------------------------------------------


class StaffListScopingTests(TwoSchoolTestCase):
    def test_school_a_staff_lists_only_school_a_rows(self):
        self.a.payment.delete()
        self.b.payment.delete()
        self.login(self.a.admin)
        for url_name, context_name, obj_attr in LIST_CASES:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200, url_name)
                ids = [obj.pk for obj in response.context[context_name]]
                self.assertIn(getattr(self.a, obj_attr).pk, ids, url_name)
                self.assertNotIn(getattr(self.b, obj_attr).pk, ids, url_name)


class PerViewQuerysetScopingTests(TwoSchoolTestCase):
    """Every class named on the card scopes its queryset, proven per class."""

    def _view_queryset(self, view_cls, user):
        view = view_cls()
        view.request = self.rf.get("/")
        view.request.user = user
        return view.get_queryset()

    def test_school_a_admin_queryset_excludes_school_b_on_every_scoped_view(self):
        for view_cls, _model, obj_attr in SCOPED_VIEW_TABLE:
            with self.subTest(view=view_cls.__name__):
                qs = self._view_queryset(view_cls, self.a.admin)
                ids = set(qs.values_list("pk", flat=True))
                self.assertIn(getattr(self.a, obj_attr).pk, ids, view_cls.__name__)
                self.assertNotIn(getattr(self.b, obj_attr).pk, ids, view_cls.__name__)

    def test_superuser_sees_both_schools_in_every_scoped_queryset(self):
        """Required case 4.

        The 29 views' role mixins (allowed_roles = SCHOOL_ADMIN/TEACHER) do
        not admit the SUPERUSER role — a superuser gets 403 at dispatch on
        every view under test (pre-existing behaviour, proven in the RED
        run), so the bypass is asserted at the queryset layer: each scoped
        view's get_queryset() with a school=None superuser returns rows from
        both schools.
        """
        for view_cls, _model, obj_attr in SCOPED_VIEW_TABLE:
            with self.subTest(view=view_cls.__name__):
                qs = self._view_queryset(view_cls, self.superuser)
                ids = set(qs.values_list("pk", flat=True))
                self.assertIn(getattr(self.a, obj_attr).pk, ids, view_cls.__name__)
                self.assertIn(getattr(self.b, obj_attr).pk, ids, view_cls.__name__)


# ---------------------------------------------------------------------------
# Required case 2 — cross-school object access is 404 and leaves rows intact
# ---------------------------------------------------------------------------


class CrossSchoolObjectAccessTests(TwoSchoolTestCase):
    def test_cross_school_update_and_delete_return_404_and_leave_rows_unchanged(self):
        self.login(self.a.admin)
        for url_name, obj_attr, action in UPDATE_DELETE_URL_CASES:
            with self.subTest(url=url_name, action=action):
                target = getattr(self.b, obj_attr)
                model = type(target)
                url = reverse(url_name, args=[target.pk])
                before = model.objects.values().get(pk=target.pk)

                get_response = self.client.get(url)
                self.assertEqual(get_response.status_code, 404, f"GET {url_name}")

                post_response = self.client.post(url, {})
                self.assertEqual(post_response.status_code, 404, f"POST {url_name}")

                after = model.objects.values().get(pk=target.pk)
                self.assertEqual(before, after, f"row mutated via {url_name}")
                self.assertTrue(
                    model.objects.filter(pk=target.pk).exists(),
                    f"row deleted via {url_name}",
                )

    def test_own_school_update_forms_render_200(self):
        """Positive control: the same URLs render fine for A's own objects."""
        self.login(self.a.admin)
        for url_name, obj_attr, action in UPDATE_DELETE_URL_CASES:
            if action != "update":
                continue
            with self.subTest(url=url_name):
                target = getattr(self.a, obj_attr)
                response = self.client.get(reverse(url_name, args=[target.pk]))
                self.assertEqual(response.status_code, 200, url_name)


# ---------------------------------------------------------------------------
# Required case 3 — CSV/PDF exports contain only the requester's school
# ---------------------------------------------------------------------------


class ReportExportScopingTests(TwoSchoolTestCase):
    def test_school_a_exports_contain_only_school_a_data(self):
        self.login(self.a.admin)
        for url_name, is_pdf in REPORT_EXPORT_CASES:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200, url_name)
                if is_pdf:
                    self.assertEqual(response["Content-Type"], "application/pdf", url_name)
                    text = _pdf_text(response.content)
                else:
                    text = response.content.decode("utf-8")
                self.assertIn(A_STUDENT_ADM_NO, text, f"A data missing from {url_name}")
                self.assertNotIn(B_STUDENT_ADM_NO, text, f"B data leaked into {url_name}")
        # Superuser note: these endpoints 403 at dispatch for the SUPERUSER
        # role (role mixins, pre-existing) — the superuser bypass for all 29
        # views is covered at the queryset layer in
        # PerViewQuerysetScopingTests.test_superuser_sees_both_schools_in_every_scoped_queryset.


# ---------------------------------------------------------------------------
# Required case 5 — the parent invoice guard still denies cross-ward access
# ---------------------------------------------------------------------------


class ParentGuardRegressionTests(TwoSchoolTestCase):
    def test_parent_in_a_cannot_open_bs_invoice_detail(self):
        self.login(self.a.parent_user)
        response = self.client.get(
            reverse("finance:invoice-detail", args=[self.b.invoice.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_parent_in_a_cannot_download_bs_receipt_pdf(self):
        self.login(self.a.parent_user)
        response = self.client.get(
            reverse("finance:payment-receipt", args=[self.b.payment.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_parent_in_a_still_sees_own_invoice_and_receipt(self):
        """Positive control: the guard denies only cross-ward access."""
        self.login(self.a.parent_user)
        detail = self.client.get(
            reverse("finance:invoice-detail", args=[self.a.invoice.pk])
        )
        self.assertEqual(detail.status_code, 200)
        receipt = self.client.get(
            reverse("finance:payment-receipt", args=[self.a.payment.pk])
        )
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt["Content-Type"], "application/pdf")


# ---------------------------------------------------------------------------
# Mixin contract — loud configuration errors, explicit bypass branches
# ---------------------------------------------------------------------------


class SchoolScopedQuerysetMixinContractTests(TwoSchoolTestCase):
    """The mixin must fail loudly on missing config and be explicit about
    the superuser / no-school branches."""

    def _make_view(self, view_cls, user):
        view = view_cls()
        view.request = self.rf.get("/")
        view.request.user = user
        return view

    @unittest.skipUnless(SchoolScopedQuerysetMixin, "SchoolScopedQuerysetMixin not implemented yet")
    def test_missing_school_lookup_fails_at_class_creation(self):
        with self.assertRaises(ImproperlyConfigured):
            class UnscopedStudentView(SchoolScopedQuerysetMixin, ListView):
                model = Student

    @unittest.skipUnless(SchoolScopedQuerysetMixin, "SchoolScopedQuerysetMixin not implemented yet")
    def test_declared_school_lookup_passes_class_creation(self):
        try:
            class ScopedStudentView(SchoolScopedQuerysetMixin, ListView):
                model = Student
                school_lookup = "school_id"
        except ImproperlyConfigured:
            self.fail("school_lookup was declared but the mixin still raised ImproperlyConfigured")

    @unittest.skipUnless(SchoolScopedQuerysetMixin, "SchoolScopedQuerysetMixin not implemented yet")
    def test_superuser_branch_returns_queryset_unfiltered_and_unchanged(self):
        view = self._make_view(CBCReportListView, self.superuser)
        base_qs = CBCReport.objects.all()
        scoped_qs = view.scope_queryset_to_school(base_qs)
        # Deliberate no-filter branch: the exact queryset object is returned,
        # no .filter() (and therefore no school clause) is applied.
        self.assertIs(scoped_qs, base_qs)
        ids = set(scoped_qs.values_list("pk", flat=True))
        self.assertIn(self.a.report.pk, ids)
        self.assertIn(self.b.report.pk, ids)

    @unittest.skipUnless(SchoolScopedQuerysetMixin, "SchoolScopedQuerysetMixin not implemented yet")
    def test_staff_queryset_is_filtered_by_their_school(self):
        view = self._make_view(CBCReportListView, self.a.admin)
        qs = view.scope_queryset_to_school(CBCReport.objects.all())
        self.assertIsNot(qs, CBCReport.objects.all())
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.a.report.pk})

    @unittest.skipUnless(SchoolScopedQuerysetMixin, "SchoolScopedQuerysetMixin not implemented yet")
    def test_unauthenticated_user_is_denied(self):
        from django.contrib.auth.models import AnonymousUser

        view = self._make_view(CBCReportListView, AnonymousUser())
        with self.assertRaises(PermissionDenied):
            view.scope_queryset_to_school(CBCReport.objects.all())

    @unittest.skipUnless(SchoolScopedQuerysetMixin, "SchoolScopedQuerysetMixin not implemented yet")
    def test_staff_user_without_school_is_treated_as_global(self):
        """Card contract: school_id is None -> no filter (deliberate branch),
        matching the shipped finance-view convention for school-less staff."""
        orphan = User.objects.create_user(
            username="admin.orphan",
            email="orphan@example.com",
            password=PASSWORD,
            role=User.Role.SCHOOL_ADMIN,
        )
        sync_role_group_membership(orphan)
        view = self._make_view(CBCReportListView, orphan)
        base_qs = CBCReport.objects.all()
        scoped_qs = view.scope_queryset_to_school(base_qs)
        self.assertIs(scoped_qs, base_qs)
        ids = set(scoped_qs.values_list("pk", flat=True))
        self.assertIn(self.a.report.pk, ids)
        self.assertIn(self.b.report.pk, ids)
