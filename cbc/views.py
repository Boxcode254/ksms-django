from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from academics.models import Subject
from cbc.forms import (
    CBCAssessmentFormSet,
    CBCCoreCompetencyFormSet,
    CBCReportCreateForm,
    CBCReportRemarksForm,
    StrandForm,
    SubStrandForm,
)
from cbc.models import (
    CBCAssessment,
    CBCCoreCompetency,
    CBCReport,
    CoreCompetency,
    Strand,
    SubStrand,
)
from cbc.services.pdf import render_report_pdf
from core.authz import RoleRequiredMixin
from core.cache_utils import CACHE_TTL_REFERENCE, reference_cache_key
from core.models import User
from core.school_scoping import SchoolScopedQuerysetMixin
from students.models import Student, StudentGuardianRelationship


# ---------------------------------------------------------------------------
# Role mixins (use the same pattern as finance / reports views)
# ---------------------------------------------------------------------------

class CBCStaffMixin(RoleRequiredMixin):
    """Admins and teachers can edit CBC reports and the strand catalog."""
    allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)


class CBCAdminMixin(RoleRequiredMixin):
    """Admin-only access (used for strand catalog write operations)."""
    allowed_roles = (User.Role.SCHOOL_ADMIN,)


# ---------------------------------------------------------------------------
# Visibility helper for read-only access to a report
# ---------------------------------------------------------------------------

def _user_can_view_report(user, report):
    """Return True if *user* is allowed to view *report*.

    Rules:
    * Admin and teacher roles see any report.
    * Student role sees only their own report.
    * Parent role sees only their wards' reports (linked via
      :class:`students.StudentGuardianRelationship`).
    """
    if not user.is_authenticated:
        return False
    if user.role in (User.Role.SCHOOL_ADMIN, User.Role.TEACHER):
        return True
    student = report.enrollment.student
    if user.role == User.Role.STUDENT:
        try:
            return user.student_profile.pk == student.pk
        except Exception:
            return False
    if user.role == User.Role.PARENT:
        try:
            guardian = user.guardian_profile
        except Exception:
            return False
        return StudentGuardianRelationship.objects.filter(
            student=student, guardian=guardian
        ).exists()
    return False


# ---------------------------------------------------------------------------
# Report list / create / edit / detail
# ---------------------------------------------------------------------------

class CBCReportListView(SchoolScopedQuerysetMixin, CBCStaffMixin, ListView):
    model = CBCReport
    # CBCReport -> enrollment (students.Enrollment) -> school
    school_lookup = "enrollment__school_id"
    template_name = "cbc/report_list.html"
    context_object_name = "reports"
    paginate_by = 25

    def get_unscoped_queryset(self):
        qs = (
            CBCReport.objects.select_related(
                "enrollment__student__user",
                "enrollment__class_section",
                "term__academic_year",
            )
            .order_by("-term__start_date", "enrollment__student__admission_number")
        )
        term_id = self.request.GET.get("term")
        if term_id:
            qs = qs.filter(term_id=term_id)
        section_id = self.request.GET.get("class_section")
        if section_id:
            qs = qs.filter(enrollment__class_section_id=section_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from academics.models import ClassSection, Term
        from django.core.cache import cache

        terms_key = reference_cache_key("terms")
        terms = cache.get(terms_key)
        if terms is None:
            terms = list(Term.objects.order_by("-academic_year__start_date", "start_date"))
            cache.set(terms_key, terms, CACHE_TTL_REFERENCE)

        cs_key = reference_cache_key("class_sections")
        class_sections = cache.get(cs_key)
        if class_sections is None:
            class_sections = list(ClassSection.objects.order_by("grade_level", "stream"))
            cache.set(cs_key, class_sections, CACHE_TTL_REFERENCE)

        context["terms"] = terms
        context["class_sections"] = class_sections
        return context


class CBCReportCreateView(CBCStaffMixin, CreateView):
    model = CBCReport
    form_class = CBCReportCreateForm
    template_name = "cbc/report_create.html"

    def get_initial(self):
        initial = super().get_initial()
        student_id = self.request.GET.get("student")
        if student_id:
            student = Student.objects.filter(pk=student_id).first()
            if student is not None:
                enrollment = student.enrollments.filter(status="active").first()
                if enrollment is not None:
                    initial["enrollment"] = enrollment.pk
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["enrollment"].queryset = form.fields["enrollment"].queryset.filter(status="active")
        return form

    def form_valid(self, form):
        # Reject duplicate (enrollment, term) up front so the user gets a
        # nicer error than the IntegrityError from the unique constraint.
        enrollment = form.cleaned_data["enrollment"]
        if CBCReport.objects.filter(
            enrollment=enrollment, term=enrollment.term
        ).exists():
            form.add_error(
                "enrollment",
                "A CBC report already exists for this student and term.",
            )
            return self.form_invalid(form)
        report = form.save()
        report.generated_by = self.request.user
        report.save(update_fields=["generated_by"])
        messages.success(self.request, "CBC report created. Add assessments below.")
        return HttpResponseRedirect(reverse("cbc:report-edit", args=[report.pk]))


class CBCReportUpdateView(CBCStaffMixin, View):
    """Single page bringing together the remarks form, assessment formset,
    and core-competency formset.

    Using a plain :class:`View` keeps the inline-formset orchestration
    explicit; the alternative (UpdateView + extra formsets in context)
    becomes confusing once we have three forms to validate together.
    """
    template_name = "cbc/report_form.html"

    def _get_report(self, pk):
        return get_object_or_404(
            CBCReport.objects.select_related(
                "enrollment__student__user",
                "enrollment__class_section",
                "term__academic_year",
            ),
            pk=pk,
        )

    def _ensure_core_competency_rows(self, report):
        """Pre-create one row per KNEC competency so the formset always shows
        the seven canonical rows. Idempotent."""
        existing = set(
            report.core_competencies.values_list("competency", flat=True)
        )
        for code, _label in CoreCompetency.choices:
            if code not in existing:
                CBCCoreCompetency.objects.create(
                    report=report, competency=code, level="ME"
                )

    def _ensure_assessment_rows(self, report):
        grade_level = report.enrollment.class_section.grade_level
        catalog = (
            Strand.objects.filter(
                grade_level=grade_level,
                subject__school=report.enrollment.school,
            )
            .select_related("subject")
            .prefetch_related("sub_strands")
            .order_by("subject__name", "order", "name")
        )
        existing = set(
            report.assessments.values_list("subject_id", "strand_id", "sub_strand_id")
        )
        new_rows = []
        for strand in catalog:
            sub_strands = list(strand.sub_strands.all())
            if sub_strands:
                for sub_strand in sub_strands:
                    key = (strand.subject_id, strand.pk, sub_strand.pk)
                    if key in existing:
                        continue
                    new_rows.append(
                        CBCAssessment(
                            report=report,
                            subject=strand.subject,
                            strand=strand,
                            sub_strand=sub_strand,
                            score=0,
                            recorded_by=self.request.user,
                        )
                    )
                    existing.add(key)
            else:
                key = (strand.subject_id, strand.pk, None)
                if key in existing:
                    continue
                new_rows.append(
                    CBCAssessment(
                        report=report,
                        subject=strand.subject,
                        strand=strand,
                        score=0,
                        recorded_by=self.request.user,
                    )
                )
                existing.add(key)
        if new_rows:
            CBCAssessment.objects.bulk_create(new_rows)

    def get(self, request, pk):
        report = self._get_report(pk)
        self._ensure_core_competency_rows(report)
        self._ensure_assessment_rows(report)
        context = self._build_context(report)
        return render(request, self.template_name, context)

    def post(self, request, pk):
        report = self._get_report(pk)
        self._ensure_core_competency_rows(report)
        self._ensure_assessment_rows(report)
        remarks_form = CBCReportRemarksForm(request.POST, instance=report)
        assessments_formset = CBCAssessmentFormSet(
            request.POST, instance=report, prefix="assess"
        )
        cc_formset = CBCCoreCompetencyFormSet(
            request.POST, instance=report, prefix="cc"
        )

        if (
            remarks_form.is_valid()
            and assessments_formset.is_valid()
            and cc_formset.is_valid()
        ):
            with transaction.atomic():
                remarks_form.save()
                assessments = assessments_formset.save(commit=False)
                for assessment in assessments:
                    if assessment.pk is None:
                        assessment.recorded_by = request.user
                    assessment.save()
                for obj in assessments_formset.deleted_objects:
                    obj.delete()
                cc_formset.save()
            messages.success(request, "CBC report saved.")
            return HttpResponseRedirect(reverse("cbc:report-detail", args=[report.pk]))

        context = self._build_context(
            report,
            remarks_form=remarks_form,
            assessments_formset=assessments_formset,
            cc_formset=cc_formset,
        )
        return render(request, self.template_name, context)

    def _build_context(
        self,
        report,
        remarks_form=None,
        assessments_formset=None,
        cc_formset=None,
    ):
        return {
            "report": report,
            "remarks_form": remarks_form or CBCReportRemarksForm(instance=report),
            "assessments_formset": assessments_formset
            or CBCAssessmentFormSet(instance=report, prefix="assess"),
            "cc_formset": cc_formset
            or CBCCoreCompetencyFormSet(instance=report, prefix="cc"),
            "subjects": Subject.objects.filter(
                school=report.enrollment.school
            ).order_by("name"),
            "strands": Strand.objects.filter(
                grade_level=report.enrollment.class_section.grade_level,
                subject__school=report.enrollment.school,
            ).select_related("subject").prefetch_related("sub_strands"),
        }


class CBCReportDetailView(LoginRequiredMixin, DetailView):
    model = CBCReport
    template_name = "cbc/report_detail.html"
    context_object_name = "report"

    def get_queryset(self):
        return CBCReport.objects.select_related(
            "enrollment__student__user",
            "enrollment__class_section",
            "enrollment__school",
            "term__academic_year",
        )

    def dispatch(self, request, *args, **kwargs):
        # LoginRequiredMixin runs first via MRO and handles unauth redirects.
        # We only need a custom check once the user is authenticated.
        if request.user.is_authenticated:
            self.object = self.get_object()
            if not _user_can_view_report(request.user, self.object):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.object
        context["assessments_by_subject"] = _group_assessments(report)
        context["core_competencies"] = list(report.core_competencies.all())
        context["can_edit"] = self.request.user.role in (
            User.Role.SCHOOL_ADMIN,
            User.Role.TEACHER,
        )
        context["can_refresh_attendance"] = context["can_edit"]
        return context


class CBCReportRefreshAttendanceView(CBCStaffMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(CBCReport, pk=pk)
        report.snapshot_attendance()
        report.save(update_fields=["total_school_days", "days_present", "updated_at"])
        messages.success(request, "Attendance snapshot refreshed.")
        return HttpResponseRedirect(reverse("cbc:report-detail", args=[report.pk]))


def _group_assessments(report):
    grouped = {}
    qs = report.assessments.select_related("subject", "strand", "sub_strand").order_by(
        "subject__name", "strand__order", "sub_strand__order"
    )
    for assessment in qs:
        grouped.setdefault(assessment.subject, []).append(assessment)
    return sorted(grouped.items(), key=lambda pair: pair[0].name)


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

class CBCReportPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(
            CBCReport.objects.select_related(
                "enrollment__student__user",
                "enrollment__class_section",
                "enrollment__school",
                "term__academic_year",
            ),
            pk=pk,
        )
        if not _user_can_view_report(request.user, report):
            raise PermissionDenied

        pdf_bytes = render_report_pdf(
            report, base_url=request.build_absolute_uri("/")
        )
        student = report.enrollment.student
        filename = (
            f"cbc-report-{student.admission_number}-"
            f"{report.term.name}-{report.term.academic_year.name}.pdf"
        )
        # Admins and teachers download; learners and parents view inline.
        disposition = (
            "attachment"
            if request.user.role in (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)
            else "inline"
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Per-student history
# ---------------------------------------------------------------------------

class StudentCBCHistoryView(LoginRequiredMixin, View):
    template_name = "cbc/student_history.html"

    def get(self, request, student_pk):
        student = get_object_or_404(Student, pk=student_pk)
        # Build a synthetic "report" check for one of the student's reports
        # to reuse the same access predicate.
        any_report = (
            CBCReport.objects.filter(enrollment__student=student).first()
        )
        if any_report and not _user_can_view_report(request.user, any_report):
            raise PermissionDenied
        if any_report is None and request.user.role not in (
            User.Role.SCHOOL_ADMIN,
            User.Role.TEACHER,
        ):
            # Student/parent with no reports yet — verify they would be
            # allowed to see this student's record.
            if request.user.role == User.Role.STUDENT:
                if not getattr(request.user, "student_profile", None) or (
                    request.user.student_profile.pk != student.pk
                ):
                    raise PermissionDenied
            elif request.user.role == User.Role.PARENT:
                guardian = getattr(request.user, "guardian_profile", None)
                if guardian is None or not StudentGuardianRelationship.objects.filter(
                    student=student, guardian=guardian
                ).exists():
                    raise PermissionDenied
            else:
                raise PermissionDenied

        reports = (
            CBCReport.objects.filter(enrollment__student=student)
            .select_related("term__academic_year", "enrollment__class_section")
            .order_by("-term__start_date")
        )
        return render(
            request,
            self.template_name,
            {"student": student, "reports": reports},
        )


# ---------------------------------------------------------------------------
# Bulk generation stub (Phase 2)
# ---------------------------------------------------------------------------

class CBCBulkGenerateStubView(CBCStaffMixin, View):
    def dispatch(self, request, *args, **kwargs):
        messages.info(
            request,
            "Bulk CBC report generation is coming soon in Phase 2.",
        )
        response = HttpResponseRedirect(reverse("cbc:report-list"))
        response.status_code = 501
        return response


# ---------------------------------------------------------------------------
# Strand catalog CRUD (admin-only writes; staff-readable list)
# ---------------------------------------------------------------------------

class StrandListView(SchoolScopedQuerysetMixin, CBCStaffMixin, ListView):
    model = Strand
    # Strand -> subject (academics.Subject) -> school
    school_lookup = "subject__school_id"
    template_name = "cbc/strand_list.html"
    context_object_name = "strands"
    paginate_by = 50

    def get_unscoped_queryset(self):
        qs = Strand.objects.select_related("subject").prefetch_related("sub_strands").order_by(
            "subject__name", "grade_level", "order", "name"
        )
        subject_id = self.request.GET.get("subject")
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        grade_level = self.request.GET.get("grade_level")
        if grade_level:
            qs = qs.filter(grade_level=grade_level)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["subjects"] = Subject.objects.order_by("name")
        return context


class StrandCreateView(CBCAdminMixin, CreateView):
    model = Strand
    form_class = StrandForm
    template_name = "cbc/strand_form.html"
    success_url = reverse_lazy("cbc:strand-list")


class StrandUpdateView(SchoolScopedQuerysetMixin, CBCAdminMixin, UpdateView):
    # Strand -> subject (academics.Subject) -> school
    school_lookup = "subject__school_id"
    model = Strand
    form_class = StrandForm
    template_name = "cbc/strand_form.html"
    success_url = reverse_lazy("cbc:strand-list")


class StrandDeleteView(SchoolScopedQuerysetMixin, CBCAdminMixin, DeleteView):
    # Strand -> subject (academics.Subject) -> school
    school_lookup = "subject__school_id"
    model = Strand
    template_name = "cbc/strand_confirm_delete.html"
    success_url = reverse_lazy("cbc:strand-list")


class SubStrandCreateView(CBCAdminMixin, CreateView):
    model = SubStrand
    form_class = SubStrandForm
    template_name = "cbc/sub_strand_form.html"
    success_url = reverse_lazy("cbc:strand-list")

    def get_initial(self):
        initial = super().get_initial()
        strand_id = self.kwargs.get("strand_pk")
        if strand_id:
            initial["strand"] = strand_id
        return initial


class SubStrandUpdateView(SchoolScopedQuerysetMixin, CBCAdminMixin, UpdateView):
    # SubStrand -> strand (cbc.Strand) -> subject -> school
    school_lookup = "strand__subject__school_id"
    model = SubStrand
    form_class = SubStrandForm
    template_name = "cbc/sub_strand_form.html"
    success_url = reverse_lazy("cbc:strand-list")


class SubStrandDeleteView(SchoolScopedQuerysetMixin, CBCAdminMixin, DeleteView):
    # SubStrand -> strand (cbc.Strand) -> subject -> school
    school_lookup = "strand__subject__school_id"
    model = SubStrand
    template_name = "cbc/sub_strand_confirm_delete.html"
    success_url = reverse_lazy("cbc:strand-list")
