import json
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from .authz import RolePermissionRequiredMixin
from .cache_utils import CACHE_TTL_DASHBOARD, dashboard_cache_key
from .models import AuditLog, School, User

logger = logging.getLogger(__name__)


from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie


class HomeView(TemplateView):
    template_name = 'core/home.html'


@method_decorator(vary_on_cookie, name='dispatch')
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_template_names(self):
        role_templates = {
            User.Role.SUPERUSER: 'core/admin_dashboard.html',
            User.Role.SCHOOL_ADMIN: 'core/admin_dashboard.html',
            User.Role.TEACHER: 'core/teacher_dashboard.html',
            User.Role.STUDENT: 'core/student_dashboard.html',
            User.Role.PARENT: 'core/parent_dashboard.html',
        }
        return [role_templates.get(self.request.user.role, 'core/dashboard.html')]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.request.user.role
        cache_key = dashboard_cache_key(self.request.user)
        cached = cache.get(cache_key)
        if cached and not getattr(settings, "DEBUG", False):
            context.update(cached)
            return context
        if role in (User.Role.SCHOOL_ADMIN, User.Role.SUPERUSER):
            data = self._admin_context()
        elif role == User.Role.TEACHER:
            data = self._teacher_context()
        elif role == User.Role.STUDENT:
            data = self._student_context()
        elif role == User.Role.PARENT:
            data = self._parent_context()
        else:
            data = {}
        cache.set(cache_key, data, CACHE_TTL_DASHBOARD)
        context.update(data)
        return context

    # ------------------------------------------------------------------
    # Admin dashboard context
    # ------------------------------------------------------------------
    def _admin_context(self):
        from academics.models import Term
        from attendance.models import AttendanceStatus, DailyAttendance
        from finance.models import FeeArrear, Invoice, Payment
        from students.models import Enrollment, Student
        from academics.models import Teacher
        from django.db.models import Q

        today = timezone.localdate()
        is_global_admin = self.request.user.is_superuser or self.request.user.role == User.Role.SUPERUSER
        school_id = None if is_global_admin else self.request.user.school_id

        # Build base school filter once
        def school_filter(qs, lookup):
            if school_id:
                return qs.filter(**{lookup: school_id})
            if not is_global_admin:
                return qs.none()
            return qs

        current_term_qs = Term.objects.filter(is_current=True).select_related('school', 'academic_year')
        current_term = school_filter(current_term_qs, 'school_id').first()

        # Attendance: 7-day chart in a SINGLE query using conditional aggregation
        week_start = today - timezone.timedelta(days=6)
        attendance_rows = (
            DailyAttendance.objects
            .filter(attendance_date__gte=week_start, attendance_date__lte=today)
        )
        attendance_rows = school_filter(attendance_rows, 'enrollment__school_id')
        attendance_agg = attendance_rows.values('attendance_date').annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status=AttendanceStatus.PRESENT)),
        ).order_by('attendance_date')

        # Build a lookup dict for the 7 days
        attendance_by_date = {row['attendance_date']: row for row in attendance_agg}
        chart_labels = []
        chart_values = []
        today_total = 0
        today_present = 0
        for offset in range(6, -1, -1):
            day = today - timezone.timedelta(days=offset)
            row = attendance_by_date.get(day, {'total': 0, 'present': 0})
            total = row['total']
            present = row['present']
            pct = round(present / total * 100) if total else 0
            chart_labels.append(day.strftime('%b %d'))
            chart_values.append(pct)
            if offset == 0:
                today_total = total
                today_present = present
        today_attendance_pct = round(today_present / today_total * 100) if today_total else None

        # Invoice breakdown: 3 counts in a SINGLE query
        invoice_base = Invoice.objects.all()
        invoice_base = school_filter(invoice_base, 'enrollment__school_id')
        if current_term:
            invoice_base = invoice_base.filter(enrollment__term=current_term)
        invoice_agg = invoice_base.aggregate(
            pending=Count('id', filter=Q(status=Invoice.Status.PENDING)),
            partial=Count('id', filter=Q(status=Invoice.Status.PARTIAL)),
            paid=Count('id', filter=Q(status=Invoice.Status.PAID)),
        )
        invoice_pending = invoice_agg['pending']
        invoice_partial = invoice_agg['partial']
        invoice_paid = invoice_agg['paid']

        # Payment aggregates
        payment_base = Payment.objects.filter(status=Payment.Status.SUCCESSFUL)
        payment_base = school_filter(payment_base, 'invoice__enrollment__school_id')
        if current_term:
            payment_base = payment_base.filter(invoice__enrollment__term=current_term)

        fees_collected_total = payment_base.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Arrears aggregate
        arrear_base = FeeArrear.objects.filter(status__in=[FeeArrear.Status.PENDING, FeeArrear.Status.OVERDUE])
        arrear_base = school_filter(arrear_base, 'school_id')
        if current_term:
            arrear_base = arrear_base.filter(invoice__enrollment__term=current_term)
        outstanding_fees_total = arrear_base.aggregate(total=Sum('outstanding_amount'))['total'] or Decimal('0.00')

        # Recent payments (still a separate query — needs related objects)
        recent_payments = (
            payment_base
            .select_related('invoice__enrollment__student__user')
            .order_by('-paid_at')[:5]
        )

        # Payment method breakdown
        payment_method_rows = (
            payment_base
            .values('payment_method')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        method_label_map = {
            Payment.Method.MPESA: 'Mobile Money',
            Payment.Method.CASH: 'Cash',
            Payment.Method.BANK: 'Bank Transfer',
            Payment.Method.CHEQUE: 'Card/Cheque',
        }
        payment_method_total = sum((row['total'] or Decimal('0.00')) for row in payment_method_rows)
        payment_method_breakdown = []
        for row in payment_method_rows:
            amount = row['total'] or Decimal('0.00')
            pct = int(round((amount / payment_method_total) * 100)) if payment_method_total else 0
            payment_method_breakdown.append({
                'label': method_label_map.get(row['payment_method'], row['payment_method'].title()),
                'amount': amount,
                'amount_display': self._kes(amount),
                'percent': pct,
            })

        # Students by class
        enrollment_base = Enrollment.objects.filter(status=Enrollment.Status.ACTIVE)
        enrollment_base = school_filter(enrollment_base, 'school_id')
        if current_term:
            enrollment_base = enrollment_base.filter(term=current_term)
        students_by_class = list(
            enrollment_base
            .values('class_section__grade_level', 'class_section__stream')
            .annotate(student_total=Count('id'))
            .order_by('class_section__grade_level', 'class_section__stream')[:10]
        )
        for row in students_by_class:
            grade = row['class_section__grade_level']
            stream = row['class_section__stream']
            row['class_display'] = f"{grade}{stream}" if stream and len(stream) <= 2 else f"{grade} {stream}"

        # Fee defaulters
        fee_defaulters = (
            arrear_base
            .select_related('student__user', 'invoice')
            .order_by('-days_overdue', '-outstanding_amount')[:8]
        )

        chart_data = json.dumps({
            'attendance': {'labels': chart_labels, 'values': chart_values},
            'invoices': {
                'labels': ['Pending', 'Partial', 'Paid'],
                'values': [invoice_pending, invoice_partial, invoice_paid],
            },
        }, cls=DjangoJSONEncoder)

        # Counts
        student_qs = Student.objects.filter(status='active')
        teacher_qs = Teacher.objects.all()
        if school_id:
            student_qs = student_qs.filter(school_id=school_id)
            teacher_qs = teacher_qs.filter(school_id=school_id)
        elif not is_global_admin:
            student_qs = student_qs.none()
            teacher_qs = teacher_qs.none()

        recent_audit_logs = []
        if is_global_admin:
            recent_audit_logs = AuditLog.objects.select_related('actor', 'content_type').order_by('-id')[:5]

        return {
            'student_count': student_qs.count(),
            'teacher_count': teacher_qs.count(),
            'current_term': current_term,
            'today_attendance_pct': today_attendance_pct,
            'today_total': today_total,
            'invoice_pending': invoice_pending,
            'invoice_partial': invoice_partial,
            'invoice_paid': invoice_paid,
            'fees_collected_total': fees_collected_total,
            'fees_collected_display': self._kes(fees_collected_total),
            'outstanding_fees_total': outstanding_fees_total,
            'outstanding_fees_display': self._kes(outstanding_fees_total),
            'recent_payments': recent_payments,
            'students_by_class': students_by_class,
            'fee_defaulters': fee_defaulters,
            'payment_method_breakdown': payment_method_breakdown,
            'recent_audit_logs': recent_audit_logs,
            'chart_data': chart_data,
        }

    @staticmethod
    def _kes(amount):
        return f"KES {Decimal(amount):,.2f}"

    # ------------------------------------------------------------------
    # Teacher dashboard context
    # ------------------------------------------------------------------
    def _teacher_context(self):
        from academics.models import Teacher, TeachingAssignment, Term, TimetableEntry
        from academics.models import GradeResult

        today = timezone.localdate()
        weekday = today.isoweekday()
        current_term = Term.objects.filter(is_current=True).first()

        teacher_profile = None
        today_timetable = []
        assignments = []
        recent_grades = []

        try:
            teacher_profile = self.request.user.teacher_profile
            assignments = (
                TeachingAssignment.objects
                .filter(teacher=teacher_profile)
                .select_related('class_section', 'subject')
                .order_by('class_section__grade_level', 'class_section__stream', 'subject__name')
            )
            if current_term:
                today_timetable = (
                    TimetableEntry.objects
                    .filter(
                        teaching_assignment__teacher=teacher_profile,
                        term=current_term,
                        weekday=weekday,
                    )
                    .select_related('teaching_assignment__class_section', 'teaching_assignment__subject')
                    .order_by('start_time')
                )
            recent_grades = (
                GradeResult.objects
                .filter(recorded_by=self.request.user)
                .select_related('enrollment__student__user', 'subject')
                .order_by('-created_at')[:5]
            )
        except User.teacher_profile.RelatedObjectDoesNotExist:
            logger.warning("Teacher dashboard: user %s has no teacher profile", self.request.user.username)
        except Exception:
            logger.exception("Teacher dashboard: unexpected error for user %s", self.request.user.username)

        return {
            'teacher_profile': teacher_profile,
            'today_timetable': today_timetable,
            'assignments': assignments,
            'recent_grades': recent_grades,
            'current_term': current_term,
            'today': today,
        }

    # ------------------------------------------------------------------
    # Student dashboard context
    # ------------------------------------------------------------------
    def _student_context(self):
        from academics.models import Term, TimetableEntry
        from academics.models import GradeResult
        from attendance.models import AttendanceStatus, DailyAttendance
        from communication.models import Announcement
        from finance.models import Invoice
        from students.models import Enrollment

        today = timezone.localdate()
        weekday = today.isoweekday()
        current_term = Term.objects.filter(is_current=True).first()

        student_profile = None
        enrollment = None
        today_timetable = []
        recent_grades = []
        monthly_attendance = []
        open_invoices = []
        announcements = []
        attendance_pct = None

        try:
            student_profile = self.request.user.student_profile
            enrollment = (
                Enrollment.objects
                .filter(student=student_profile, status=Enrollment.Status.ACTIVE)
                .select_related('class_section', 'term', 'academic_year')
                .first()
            )
            if enrollment and current_term:
                today_timetable = (
                    TimetableEntry.objects
                    .filter(
                        teaching_assignment__class_section=enrollment.class_section,
                        term=current_term,
                        weekday=weekday,
                    )
                    .select_related(
                        'teaching_assignment__subject',
                        'teaching_assignment__teacher__user',
                    )
                    .order_by('start_time')
                )
            if enrollment:
                recent_grades = (
                    GradeResult.objects
                    .filter(enrollment=enrollment)
                    .select_related('subject')
                    .order_by('-created_at')[:5]
                )
                month_start = today.replace(day=1)
                monthly_attendance = (
                    DailyAttendance.objects
                    .filter(enrollment=enrollment, attendance_date__gte=month_start)
                    .select_related("enrollment__class_section")
                    .order_by("-attendance_date")
                )
                total = monthly_attendance.count()
                present = monthly_attendance.filter(status=AttendanceStatus.PRESENT).count()
                attendance_pct = round(present / total * 100) if total else None

                open_invoices = (
                    Invoice.objects
                    .filter(
                        enrollment__student=student_profile,
                        status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL],
                    )
                    .order_by('due_date')[:3]
                )

            school = student_profile.school if student_profile else None
            if school:
                announcements = (
                    Announcement.objects
                    .filter(
                        school=school,
                        is_active=True,
                        audience__in=[Announcement.Audience.ALL, Announcement.Audience.STUDENTS],
                    )
                    .order_by('-created_at')[:3]
                )
        except User.student_profile.RelatedObjectDoesNotExist:
            logger.warning("Student dashboard: user %s has no student profile", self.request.user.username)
        except Exception:
            logger.exception("Student dashboard: unexpected error for user %s", self.request.user.username)

        # Academic average from recent grades
        academic_avg = None
        if recent_grades:
            scores = [float(g.score) for g in recent_grades]
            academic_avg = round(sum(scores) / len(scores), 1)

        # Total outstanding balance
        fees_balance = sum(inv.balance for inv in open_invoices)

        return {
            'student_profile': student_profile,
            'enrollment': enrollment,
            'today_timetable': today_timetable,
            'recent_grades': recent_grades,
            'monthly_attendance': monthly_attendance,
            'attendance_pct': attendance_pct,
            'open_invoices': open_invoices,
            'fees_balance': fees_balance,
            'announcements': announcements,
            'academic_avg': academic_avg,
            'current_term': current_term,
            'today': today,
        }

    # ------------------------------------------------------------------
    # Parent dashboard context
    # ------------------------------------------------------------------
    def _parent_context(self):
        from attendance.models import DailyAttendance
        from communication.models import Announcement
        from finance.models import Invoice, Payment
        from students.models import Enrollment, StudentGuardianRelationship

        school = None
        children_data = []
        announcements = []

        try:
            guardian = self.request.user.guardian_profile
            school = guardian.school
            relationships = (
                StudentGuardianRelationship.objects
                .filter(guardian=guardian)
                .select_related(
                    'student__user',
                    'student__school',
                )
                .order_by('-is_primary_contact', 'student__user__first_name')
            )
            students = [rel.student for rel in relationships]
            student_ids = [student.id for student in students]

            enrollments = (
                Enrollment.objects
                .filter(student_id__in=student_ids, status=Enrollment.Status.ACTIVE)
                .select_related('class_section', 'term', 'academic_year')
            )
            enrollment_by_student_id = {enrollment.student_id: enrollment for enrollment in enrollments}

            open_invoices = (
                Invoice.objects
                .filter(
                    enrollment__student_id__in=student_ids,
                    status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL],
                )
                .select_related('enrollment')
            )
            balance_by_student_id = {}
            for invoice in open_invoices:
                sid = invoice.enrollment.student_id
                balance_by_student_id[sid] = balance_by_student_id.get(sid, 0) + invoice.balance

            latest_payments = (
                Payment.objects
                .filter(
                    invoice__enrollment__student_id__in=student_ids,
                    status=Payment.Status.SUCCESSFUL,
                )
                .select_related('invoice', 'received_by')
                .order_by('invoice__enrollment__student_id', '-paid_at')
            )
            latest_payment_by_student_id = {}
            for payment in latest_payments:
                sid = payment.invoice.enrollment.student_id
                latest_payment_by_student_id.setdefault(sid, payment)

            attendance_rows = (
                DailyAttendance.objects
                .filter(enrollment__student_id__in=student_ids)
                .select_related("enrollment__class_section", "enrollment__term")
                .order_by("enrollment__student_id", "-attendance_date")
            )
            attendance_by_student_id = {}
            for row in attendance_rows:
                sid = row.enrollment.student_id
                entries = attendance_by_student_id.setdefault(sid, [])
                if len(entries) < 5:
                    entries.append(row)

            for rel in relationships:
                student = rel.student
                enrollment = enrollment_by_student_id.get(student.id)
                total_balance = balance_by_student_id.get(student.id, 0)
                recent_attendance = attendance_by_student_id.get(student.id, [])
                latest_payment = latest_payment_by_student_id.get(student.id)
                children_data.append({
                    'student': student,
                    'enrollment': enrollment,
                    'total_balance': total_balance,
                    'recent_attendance': recent_attendance,
                    'latest_payment': latest_payment,
                    'relationship': rel.get_relationship_display(),
                })
            if school:
                announcements = (
                    Announcement.objects
                    .filter(
                        school=school,
                        is_active=True,
                        audience__in=[Announcement.Audience.ALL, Announcement.Audience.PARENTS],
                    )
                    .order_by('-created_at')[:3]
                )
        except User.guardian_profile.RelatedObjectDoesNotExist:
            logger.warning("Parent dashboard: user %s has no guardian profile", self.request.user.username)
        except Exception:
            logger.exception("Parent dashboard: unexpected error for user %s", self.request.user.username)

        return {
            'children_data': children_data,
            'announcements': announcements,
        }


class AuditLogListView(RolePermissionRequiredMixin, ListView):
    model = AuditLog
    template_name = 'core/audit_log_list.html'
    context_object_name = 'audit_logs'
    paginate_by = 25
    allowed_roles = (User.Role.SUPERUSER,)
    permission_required = 'core.view_auditlog'

    def get_queryset(self):
        return AuditLog.objects.select_related('actor', 'content_type')


class SchoolBackupDownloadView(LoginRequiredMixin, View):
    """Download a school-scoped JSON backup for local or cloud storage."""

    allowed_roles = {User.Role.SCHOOL_ADMIN, User.Role.SUPERUSER}

    SCHEMA_VERSION = "2026.05.10"

    def get(self, request, *args, **kwargs):
        if request.user.role not in self.allowed_roles:
            return HttpResponse(status=403)

        school = self._resolve_school(request)
        if school is None:
            return HttpResponse('No school context available for backup.', status=400)

        from django.db.models import Max
        from academics.models import AcademicYear, ClassSection, Subject, Teacher, Term
        from finance.models import FeeArrear, FeeStructure, Invoice, Payment
        from students.models import Enrollment, Guardian, Student

        qs_map = {
            'academic_years': AcademicYear.objects.filter(school=school),
            'terms': Term.objects.filter(school=school),
            'class_sections': ClassSection.objects.filter(school=school),
            'subjects': Subject.objects.filter(school=school),
            'teachers': Teacher.objects.filter(school=school),
            'students': Student.objects.filter(school=school),
            'guardians': Guardian.objects.filter(school=school),
            'enrollments': Enrollment.objects.filter(school=school),
            'fee_structures': FeeStructure.objects.filter(school=school),
            'invoices': Invoice.objects.filter(enrollment__school=school),
            'payments': Payment.objects.filter(invoice__enrollment__school=school),
            'fee_arrears': FeeArrear.objects.filter(school=school),
        }

        record_counts = {key: qs.count() for key, qs in qs_map.items()}

        max_updated = None
        for qs in qs_map.values():
            agg = qs.aggregate(m=Max('updated_at'))
            if agg['m']:
                max_updated = max(max_updated, agg['m']) if max_updated else agg['m']

        payload = {
            'meta': {
                'app': 'EduTrack SMS',
                'backup_type': 'school_scoped_json',
                'schema_version': self.SCHEMA_VERSION,
                'generated_at': timezone.now().isoformat(),
                'generated_by': request.user.username,
                'school': {
                    'id': school.id,
                    'name': school.name,
                    'code': school.code,
                    'slug': school.slug,
                },
                'record_counts': record_counts,
                'max_updated_at': max_updated.isoformat() if max_updated else None,
                'cloud_ready': True,
            },
            'data': {key: list(qs.values()) for key, qs in qs_map.items()},
        }

        backup_json = json.dumps(payload, cls=DjangoJSONEncoder, indent=2)
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{school.slug}_backup_{timestamp}.json"

        response = HttpResponse(backup_json, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _resolve_school(self, request):
        # School admins are restricted to their own school; superusers may choose via query string.
        if request.user.role == User.Role.SCHOOL_ADMIN:
            return request.user.school

        school_id = request.GET.get('school_id')
        if school_id:
            return School.objects.filter(pk=school_id).first()
        return request.user.school


def health_check(request):
    """Lightweight health check for load balancers and uptime monitors.

    Returns 200 if the database is reachable, 503 otherwise.
    No authentication required — this endpoint exposes no sensitive data.
    """
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok", "database": "connected"})
    except Exception as exc:
        return JsonResponse({"status": "error", "database": str(exc)}, status=503)


def web_manifest(request):
    school = School.objects.filter(is_active=True).order_by('name').first()
    school_name = school.name if school else 'School'
    data = {
        'name': f'KSMS - {school_name}',
        'short_name': 'KSMS',
        'description': 'Kenya School Management System',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#f8fafc',
        'theme_color': '#0f172a',
        'icons': [
            {
                'src': f"{settings.STATIC_URL}pwa/icon-192.svg",
                'sizes': '192x192',
                'type': 'image/svg+xml',
                'purpose': 'any maskable',
            },
            {
                'src': f"{settings.STATIC_URL}pwa/icon-512.svg",
                'sizes': '512x512',
                'type': 'image/svg+xml',
                'purpose': 'any maskable',
            },
        ],
    }
    return JsonResponse(data)


def service_worker(request):
    script = render_to_string(
        'core/service-worker.js',
        {
            'static_url': settings.STATIC_URL,
        },
    )
    return HttpResponse(script, content_type='application/javascript')


from django.conf import settings
from django.http import Http404
from django.views.static import serve


def secure_media_serve(request, path):
    if not request.user.is_authenticated:
        raise Http404("Media files require authentication.")
    full_path = settings.MEDIA_ROOT / path
    if not full_path.exists():
        raise Http404("File not found.")
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
