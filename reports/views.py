import csv
import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import ListView, TemplateView
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from academics.models import ClassSection, GradeResult, Term
from academics.services import build_report_card_subject_rows, resolve_mean_grade
from attendance.models import AttendanceStatus, DailyAttendance
from core.authz import RolePermissionRequiredMixin
from core.cache_utils import CACHE_TTL_REFERENCE, reference_cache_key
from core.models import AuditLog, School, User
from core.request_context import get_client_ip, get_user_agent
from finance.models import Invoice
from students.models import Enrollment, Student


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class ReportsAdminTeacherMixin(RolePermissionRequiredMixin):
    allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)


class ReportsAdminOnlyMixin(RolePermissionRequiredMixin):
    allowed_roles = (User.Role.SCHOOL_ADMIN,)


def _get_cached_schools():
    key = reference_cache_key("schools")
    result = cache.get(key)
    if result is None:
        result = list(School.objects.filter(is_active=True).order_by("name"))
        cache.set(key, result, CACHE_TTL_REFERENCE)
    return result


def _get_cached_terms():
    key = reference_cache_key("terms")
    result = cache.get(key)
    if result is None:
        result = list(Term.objects.select_related("academic_year").order_by("-academic_year__start_date"))
        cache.set(key, result, CACHE_TTL_REFERENCE)
    return result


def _get_cached_class_sections():
    key = reference_cache_key("class_sections")
    result = cache.get(key)
    if result is None:
        result = list(ClassSection.objects.select_related("academic_year").order_by("grade_level", "stream"))
        cache.set(key, result, CACHE_TTL_REFERENCE)
    return result


def _csv_response(filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _pdf_response(filename):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _apply_export_limit(qs):
    total_count = qs.count()
    limit = getattr(settings, 'EXPORT_ROW_LIMIT', 5000)
    truncated = total_count > limit
    if truncated:
        qs = qs[:limit]
    return qs, total_count, truncated, limit


def _build_pdf_report(response, title, headers, rows):
    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        leftMargin=1 * cm,
        rightMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles['Title']),
        Spacer(1, 0.4 * cm),
    ]
    table_data = [headers, *rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    doc.build(story)


def _parse_date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _log_report_export(request, report_name, export_format, row_count):
    user = request.user if request.user.is_authenticated else None
    AuditLog.objects.create(
        actor=user,
        action=AuditLog.Action.UPDATE,
        object_repr=f'{report_name} ({export_format})',
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata={
            'event': 'report_export',
            'report': report_name,
            'format': export_format,
            'row_count': row_count,
            'query': request.GET.urlencode(),
        },
    )


def _attendance_filtered_qs(request):
    qs = DailyAttendance.objects.select_related(
        'enrollment__student__user',
        'enrollment__class_section',
        'enrollment__term',
    ).order_by('-attendance_date')

    q = request.GET.get('q', '').strip()
    school_id = request.GET.get('school')
    term_id = request.GET.get('term')
    class_id = request.GET.get('class_section')
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    status = request.GET.get('status', '').strip()

    if q:
        qs = qs.filter(
            Q(enrollment__student__user__first_name__icontains=q)
            | Q(enrollment__student__user__last_name__icontains=q)
            | Q(enrollment__student__admission_number__icontains=q)
        )
    if school_id:
        qs = qs.filter(enrollment__school_id=school_id)
    if term_id:
        qs = qs.filter(enrollment__term_id=term_id)
    if class_id:
        qs = qs.filter(enrollment__class_section_id=class_id)
    if date_from:
        qs = qs.filter(attendance_date__gte=date_from)
    if date_to:
        qs = qs.filter(attendance_date__lte=date_to)
    if status:
        qs = qs.filter(status=status)
    return qs


def _fee_filtered_qs(request):
    qs = Invoice.objects.select_related(
        'enrollment__student__user',
        'enrollment__class_section',
        'enrollment__term',
        'fee_structure',
    ).order_by('-created_at')

    school_id = request.GET.get('school')
    term_id = request.GET.get('term')
    status = request.GET.get('status', '').strip()
    q = request.GET.get('q', '').strip()

    if school_id:
        qs = qs.filter(enrollment__school_id=school_id)
    if term_id:
        qs = qs.filter(enrollment__term_id=term_id)
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(invoice_number__icontains=q)
            | Q(enrollment__student__user__first_name__icontains=q)
            | Q(enrollment__student__user__last_name__icontains=q)
            | Q(enrollment__student__admission_number__icontains=q)
        )
    return qs


def _student_register_filtered_qs(request):
    qs = Enrollment.objects.select_related(
        'student__user',
        'class_section',
        'term',
        'academic_year',
    ).order_by('class_section__grade_level', 'class_section__stream', 'student__admission_number')

    school_id = request.GET.get('school')
    term_id = request.GET.get('term')
    class_id = request.GET.get('class_section')
    status = request.GET.get('status', 'active').strip()
    q = request.GET.get('q', '').strip()

    if school_id:
        qs = qs.filter(school_id=school_id)
    if term_id:
        qs = qs.filter(term_id=term_id)
    if class_id:
        qs = qs.filter(class_section_id=class_id)
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(student__user__first_name__icontains=q)
            | Q(student__user__last_name__icontains=q)
            | Q(student__admission_number__icontains=q)
        )
    return qs


def _academic_summary_filtered_qs(request):
    qs = GradeResult.objects.select_related(
        'enrollment__student__user',
        'enrollment__class_section',
        'enrollment__term',
        'subject',
    ).order_by('subject__name', '-score')

    school_id = request.GET.get('school')
    term_id = request.GET.get('term')
    class_id = request.GET.get('class_section')
    subject_id = request.GET.get('subject')
    exam_type = request.GET.get('exam_type')
    q = request.GET.get('q', '').strip()

    if school_id:
        qs = qs.filter(enrollment__school_id=school_id)
    if term_id:
        qs = qs.filter(enrollment__term_id=term_id)
    if class_id:
        qs = qs.filter(enrollment__class_section_id=class_id)
    if subject_id:
        qs = qs.filter(subject_id=subject_id)
    if exam_type:
        qs = qs.filter(exam_type=exam_type)
    if q:
        qs = qs.filter(
            Q(enrollment__student__user__first_name__icontains=q)
            | Q(enrollment__student__user__last_name__icontains=q)
            | Q(enrollment__student__admission_number__icontains=q)
        )
    return qs


# ---------------------------------------------------------------------------
# Attendance Report
# ---------------------------------------------------------------------------

class AttendanceReportView(ReportsAdminTeacherMixin, ListView):
    model = DailyAttendance
    template_name = 'reports/attendance_report.html'
    context_object_name = 'records'
    paginate_by = 50
    permission_required = 'attendance.view_dailyattendance'

    def get_queryset(self):
        qs = _attendance_filtered_qs(self.request)
        self._qs = qs
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self._qs
        total = qs.count()
        present = qs.filter(status=AttendanceStatus.PRESENT).count()
        absent = qs.filter(status=AttendanceStatus.ABSENT).count()
        context.update({
            'page_title': 'Attendance Report',
            'schools': _get_cached_schools(),
            'terms': _get_cached_terms(),
            'class_sections': _get_cached_class_sections(),
            'status_choices': AttendanceStatus.choices,
            'total': total,
            'present_count': present,
            'absent_count': absent,
            'present_pct': round(present / total * 100) if total else None,
            'csv_url': self.request.get_full_path().replace('/reports/attendance/', '/reports/attendance/csv/').split('?')[0]
                       + '?' + self.request.GET.urlencode(),
            'pdf_url': self.request.get_full_path().replace('/reports/attendance/', '/reports/attendance/pdf/').split('?')[0]
                       + '?' + self.request.GET.urlencode(),
        })
        return context


class AttendanceReportCSVView(ReportsAdminTeacherMixin, ListView):
    model = DailyAttendance
    permission_required = 'attendance.view_dailyattendance'

    def get(self, request, *args, **kwargs):
        qs = _attendance_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _csv_response('attendance_report.csv')
        writer = csv.writer(response)
        writer.writerow(['Date', 'Student', 'Admission No', 'Class', 'Term', 'Status', 'Remarks'])
        row_count = 0
        for r in qs:
            writer.writerow([
                r.attendance_date,
                r.enrollment.student.user.get_full_name() or r.enrollment.student.user.username,
                r.enrollment.student.admission_number,
                r.enrollment.class_section.display_name,
                r.enrollment.term.get_name_display(),
                r.get_status_display(),
                r.remarks,
            ])
            row_count += 1
        if truncated:
            writer.writerow([])
            writer.writerow([f'Export limited to {limit} of {total_count} rows. Refine your filters.'])
        _log_report_export(request, 'attendance', 'csv', row_count)
        return response


class AttendanceReportPDFView(ReportsAdminTeacherMixin, ListView):
    model = DailyAttendance
    permission_required = 'attendance.view_dailyattendance'

    def get(self, request, *args, **kwargs):
        qs = _attendance_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _pdf_response('attendance_report.pdf')
        rows = []
        for r in qs:
            rows.append([
                str(r.attendance_date),
                r.enrollment.student.user.get_full_name() or r.enrollment.student.user.username,
                r.enrollment.student.admission_number,
                r.enrollment.class_section.display_name,
                r.enrollment.term.get_name_display(),
                r.get_status_display(),
                r.remarks or '-',
            ])
        if truncated:
            rows.append([f'Limited to {limit} of {total_count} rows', '', '', '', '', '', 'Refine filters'])
        _build_pdf_report(
            response,
            'Attendance Report',
            ['Date', 'Student', 'Admission No', 'Class', 'Term', 'Status', 'Remarks'],
            rows,
        )
        _log_report_export(request, 'attendance', 'pdf', len(rows))
        return response


# ---------------------------------------------------------------------------
# Fee Report
# ---------------------------------------------------------------------------

class FeeReportView(ReportsAdminOnlyMixin, ListView):
    model = Invoice
    template_name = 'reports/fee_report.html'
    context_object_name = 'invoices'
    paginate_by = 50
    permission_required = 'finance.view_invoice'

    def get_queryset(self):
        qs = _fee_filtered_qs(self.request)
        self._qs = qs
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.db.models import Sum
        qs = self._qs
        agg = qs.aggregate(
            total_due=Sum('amount_due'),
            total_paid=Sum('amount_paid'),
        )
        total_due = agg['total_due'] or 0
        total_paid = agg['total_paid'] or 0
        context.update({
            'page_title': 'Fee Collection Report',
            'schools': _get_cached_schools(),
            'terms': _get_cached_terms(),
            'status_choices': Invoice.Status.choices,
            'total_due': total_due,
            'total_paid': total_paid,
            'total_outstanding': total_due - total_paid,
            'invoice_count': qs.count(),
        })
        return context


class FeeReportCSVView(ReportsAdminOnlyMixin, ListView):
    model = Invoice
    permission_required = 'finance.view_invoice'

    def get(self, request, *args, **kwargs):
        qs = _fee_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _csv_response('fee_report.csv')
        writer = csv.writer(response)
        writer.writerow(['Invoice No', 'Student', 'Admission No', 'Class', 'Term', 'Amount Due', 'Amount Paid', 'Balance', 'Status', 'Due Date'])
        row_count = 0
        for inv in qs:
            writer.writerow([
                inv.invoice_number,
                inv.enrollment.student.user.get_full_name() or inv.enrollment.student.user.username,
                inv.enrollment.student.admission_number,
                inv.enrollment.class_section.display_name,
                inv.enrollment.term.get_name_display(),
                inv.amount_due,
                inv.amount_paid,
                inv.balance,
                inv.get_status_display(),
                inv.due_date,
            ])
            row_count += 1
        if truncated:
            writer.writerow([])
            writer.writerow([f'Export limited to {limit} of {total_count} rows. Refine your filters.'])
        _log_report_export(request, 'fees', 'csv', row_count)
        return response


class FeeReportPDFView(ReportsAdminOnlyMixin, ListView):
    model = Invoice
    permission_required = 'finance.view_invoice'

    def get(self, request, *args, **kwargs):
        qs = _fee_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _pdf_response('fee_report.pdf')
        rows = []
        for inv in qs:
            rows.append([
                inv.invoice_number,
                inv.enrollment.student.user.get_full_name() or inv.enrollment.student.user.username,
                inv.enrollment.student.admission_number,
                inv.enrollment.class_section.display_name,
                inv.enrollment.term.get_name_display(),
                f'{inv.amount_due}',
                f'{inv.amount_paid}',
                f'{inv.balance}',
                inv.get_status_display(),
                str(inv.due_date or ''),
            ])
        if truncated:
            rows.append([f'Limited to {limit} of {total_count} rows', '', '', '', '', '', '', '', '', 'Refine filters'])
        _build_pdf_report(
            response,
            'Fee Collection Report',
            ['Invoice No', 'Student', 'Admission No', 'Class', 'Term', 'Amount Due', 'Amount Paid', 'Balance', 'Status', 'Due Date'],
            rows,
        )
        _log_report_export(request, 'fees', 'pdf', len(rows))
        return response


# ---------------------------------------------------------------------------
# Student Register
# ---------------------------------------------------------------------------

class StudentRegisterView(ReportsAdminTeacherMixin, ListView):
    model = Enrollment
    template_name = 'reports/student_register.html'
    context_object_name = 'enrollments'
    paginate_by = 50
    permission_required = ('students.view_enrollment', 'students.view_student')

    def get_queryset(self):
        qs = _student_register_filtered_qs(self.request)
        self._qs = qs
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': 'Student Register',
            'schools': _get_cached_schools(),
            'terms': _get_cached_terms(),
            'class_sections': _get_cached_class_sections(),
            'status_choices': Enrollment.Status.choices,
            'total': self._qs.count(),
        })
        return context


class StudentRegisterCSVView(ReportsAdminTeacherMixin, ListView):
    model = Enrollment
    permission_required = ('students.view_enrollment', 'students.view_student')

    def get(self, request, *args, **kwargs):
        qs = _student_register_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _csv_response('student_register.csv')
        writer = csv.writer(response)
        writer.writerow(['Admission No', 'First Name', 'Last Name', 'Class', 'Term', 'Status', 'Start Date'])
        row_count = 0
        for enr in qs:
            writer.writerow([
                enr.student.admission_number,
                enr.student.user.first_name,
                enr.student.user.last_name,
                enr.class_section.display_name,
                enr.term.get_name_display(),
                enr.get_status_display(),
                enr.start_date,
            ])
            row_count += 1
        if truncated:
            writer.writerow([])
            writer.writerow([f'Export limited to {limit} of {total_count} rows. Refine your filters.'])
        _log_report_export(request, 'students', 'csv', row_count)
        return response


class StudentRegisterPDFView(ReportsAdminTeacherMixin, ListView):
    model = Enrollment
    permission_required = ('students.view_enrollment', 'students.view_student')

    def get(self, request, *args, **kwargs):
        qs = _student_register_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _pdf_response('student_register.pdf')
        rows = []
        for enr in qs:
            rows.append([
                enr.student.admission_number,
                enr.student.user.first_name,
                enr.student.user.last_name,
                enr.class_section.display_name,
                enr.term.get_name_display(),
                enr.get_status_display(),
                str(enr.start_date),
            ])
        if truncated:
            rows.append([f'Limited to {limit} of {total_count} rows', '', '', '', '', '', 'Refine filters'])
        _build_pdf_report(
            response,
            'Student Register',
            ['Admission No', 'First Name', 'Last Name', 'Class', 'Term', 'Status', 'Start Date'],
            rows,
        )
        _log_report_export(request, 'students', 'pdf', len(rows))
        return response


# ---------------------------------------------------------------------------
# Academic Summary
# ---------------------------------------------------------------------------

class AcademicSummaryView(ReportsAdminTeacherMixin, ListView):
    model = GradeResult
    template_name = 'reports/academic_summary.html'
    context_object_name = 'results'
    paginate_by = 50
    permission_required = 'academics.view_graderesult'

    def get_queryset(self):
        qs = _academic_summary_filtered_qs(self.request)
        self._qs = qs
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from academics.models import Subject
        agg = self._qs.aggregate(avg_score=Avg('score'))
        context.update({
            'page_title': 'Academic Performance Summary',
            'schools': _get_cached_schools(),
            'terms': _get_cached_terms(),
            'class_sections': _get_cached_class_sections(),
            'subjects': Subject.objects.filter(is_active=True).order_by("name"),
            'exam_type_choices': GradeResult.ExamType.choices,
            'total': self._qs.count(),
            'avg_score': round(float(agg['avg_score']), 1) if agg['avg_score'] else None,
        })
        return context


class AcademicSummaryCSVView(ReportsAdminTeacherMixin, ListView):
    model = GradeResult
    permission_required = 'academics.view_graderesult'

    def get(self, request, *args, **kwargs):
        qs = _academic_summary_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _csv_response('academic_summary.csv')
        writer = csv.writer(response)
        writer.writerow(['Student', 'Admission No', 'Class', 'Term', 'Subject', 'Exam Type', 'Score', 'Grade', 'Remarks'])
        row_count = 0
        for r in qs:
            writer.writerow([
                r.enrollment.student.user.get_full_name() or r.enrollment.student.user.username,
                r.enrollment.student.admission_number,
                r.enrollment.class_section.display_name,
                r.enrollment.term.get_name_display(),
                r.subject.name,
                r.get_exam_type_display(),
                r.score,
                r.grade,
                r.remarks,
            ])
            row_count += 1
        if truncated:
            writer.writerow([])
            writer.writerow([f'Export limited to {limit} of {total_count} rows. Refine your filters.'])
        _log_report_export(request, 'academics', 'csv', row_count)
        return response


class AcademicSummaryPDFView(ReportsAdminTeacherMixin, ListView):
    model = GradeResult
    permission_required = 'academics.view_graderesult'

    def get(self, request, *args, **kwargs):
        qs = _academic_summary_filtered_qs(request)
        qs, total_count, truncated, limit = _apply_export_limit(qs)

        response = _pdf_response('academic_summary.pdf')
        rows = []
        for r in qs:
            rows.append([
                r.enrollment.student.user.get_full_name() or r.enrollment.student.user.username,
                r.enrollment.student.admission_number,
                r.enrollment.class_section.display_name,
                r.enrollment.term.get_name_display(),
                r.subject.name,
                r.get_exam_type_display(),
                f'{r.score}',
                r.grade or '-',
                r.remarks or '-',
            ])
        if truncated:
            rows.append([f'Limited to {limit} of {total_count} rows', '', '', '', '', '', '', '', 'Refine filters'])
        _build_pdf_report(
            response,
            'Academic Performance Summary',
            ['Student', 'Admission No', 'Class', 'Term', 'Subject', 'Exam Type', 'Score', 'Grade', 'Remarks'],
            rows,
        )
        _log_report_export(request, 'academics', 'pdf', len(rows))
        return response


# ---------------------------------------------------------------------------
# Student Report Card
# ---------------------------------------------------------------------------

class StudentReportCardView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/report_card.html'

    def dispatch(self, request, *args, **kwargs):
        student = get_object_or_404(Student, pk=kwargs['pk'])
        user = request.user

        if not user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

        # Admin or teacher: unrestricted
        if user.role in (User.Role.SCHOOL_ADMIN, User.Role.TEACHER):
            self.student = student
            return super().dispatch(request, *args, **kwargs)

        # Student: own record only
        if user.role == User.Role.STUDENT:
            try:
                if user.student_profile.pk == student.pk:
                    self.student = student
                    return super().dispatch(request, *args, **kwargs)
            except Exception:
                pass
            raise PermissionDenied

        raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.student
        school = student.school
        enrollment = (
            Enrollment.objects
            .filter(student=student, status=Enrollment.Status.ACTIVE)
            .select_related('class_section', 'term', 'academic_year')
            .first()
        )
        grade_results = GradeResult.objects.filter(enrollment__student=student)
        if enrollment:
            grade_results = grade_results.filter(enrollment=enrollment)
        grade_results = grade_results.select_related('subject', 'enrollment__term', 'enrollment__class_section')

        subject_rows = build_report_card_subject_rows(grade_results=grade_results, school=school)
        points_values = [row['points'] for row in subject_rows if row['points'] is not None]
        mean_points = round(sum(points_values) / len(points_values), 2) if points_values else None
        mean_grade = resolve_mean_grade(mean_points, school) if mean_points is not None else None

        attendance_qs = DailyAttendance.objects.filter(enrollment__student=student)
        total_att = attendance_qs.count()
        present_att = attendance_qs.filter(status=AttendanceStatus.PRESENT).count()
        att_pct = round(present_att / total_att * 100) if total_att else None

        context.update({
            'student': student,
            'school': school,
            'enrollment': enrollment,
            'grade_results': grade_results,
            'subject_rows': subject_rows,
            'exam_type_choices': GradeResult.ExamType.choices,
            'mean_points': mean_points,
            'mean_grade': mean_grade,
            'total_attendance': total_att,
            'present_attendance': present_att,
            'attendance_pct': att_pct,
            'print_view': True,
        })
        return context
