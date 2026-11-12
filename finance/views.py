from datetime import timedelta
from decimal import Decimal, InvalidOperation
import hmac
import json
import csv

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Prefetch, Q, Sum
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View
from django.views.decorators.csrf import csrf_exempt

from core.authz import RolePermissionRequiredMixin
from core.models import AuditLog, School, User
from core.ratelimit import check_rate_limit
from core.request_context import get_client_ip, get_user_agent
from core.school_scoping import SchoolScopedQuerysetMixin
from core.validators import kenya_phone_validator
from core.views_mixins import HtmxTemplateMixin, SuccessMessageFormMixin, htmx_redirect
from reports.views import _build_pdf_report, _pdf_response
from students.models import StudentGuardianRelationship

from .forms import (
    FeeStructureFilterForm,
    FeeStructureForm,
    InvoiceFilterForm,
    InvoiceForm,
    PaymentForm,
    ReminderPolicyForm,
)
from .models import FeeArrear, FeeStructure, Invoice, Payment, ReminderPolicy
from .services.mpesa import (
    MpesaService,
    MpesaServiceError,
    generate_callback_token,
    validate_callback_token,
)
from .services.notifications import ReminderService
from .tasks import send_payment_receipt_task


def _parent_student_ids(user):
    try:
        guardian = user.guardian_profile
    except Exception:
        return StudentGuardianRelationship.objects.none().values_list("student_id", flat=True)
    return StudentGuardianRelationship.objects.filter(guardian=guardian).values_list("student_id", flat=True)


def _enforce_parent_invoice_access(user, invoice):
    if user.role != User.Role.PARENT:
        return
    linked = StudentGuardianRelationship.objects.filter(
        guardian=user.guardian_profile,
        student=invoice.enrollment.student,
    ).exists()
    if not linked:
        raise PermissionDenied


def _create_audit_log(*, request, actor, object_repr, metadata):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=AuditLog.Action.UPDATE,
        object_repr=object_repr,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Role mixins
# ---------------------------------------------------------------------------

class FinanceReadMixin(RolePermissionRequiredMixin):
    allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.PARENT)


class FinanceAdminTeacherReadMixin(RolePermissionRequiredMixin):
    allowed_roles = (User.Role.SCHOOL_ADMIN,)


class FinanceAdminWriteMixin(RolePermissionRequiredMixin):
    allowed_roles = (User.Role.SCHOOL_ADMIN,)


# ---------------------------------------------------------------------------
# Context mixins
# ---------------------------------------------------------------------------

class FinanceListContextMixin:
    page_title = ""
    create_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["page_title"] = self.page_title
        context["create_url"] = reverse(self.create_url_name) if self.create_url_name else ""
        return context


class FinanceFormContextMixin:
    form_title = ""
    submit_label = ""
    list_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = self.form_title
        context["submit_label"] = self.submit_label
        context["cancel_url"] = reverse(self.list_url_name)
        return context


# ---------------------------------------------------------------------------
# Fee Structure views
# ---------------------------------------------------------------------------

class FeeStructureListView(HtmxTemplateMixin, FinanceListContextMixin, FinanceAdminTeacherReadMixin, ListView):
    model = FeeStructure
    template_name = "finance/feestructure_list.html"
    htmx_template_name = "finance/partials/feestructure_results.html"
    context_object_name = "fee_structures"
    paginate_by = 15
    page_title = "Fee structures"
    create_url_name = "finance:feestructure-create"
    permission_required = "finance.view_feestructure"

    def get_queryset(self):
        self.filter_form = FeeStructureFilterForm(self.request.GET or None, user=self.request.user)
        queryset = FeeStructure.objects.select_related(
            "school",
            "academic_year",
            "term",
            "class_section",
        )

        if self.filter_form.is_valid():
            query = self.filter_form.cleaned_data.get("q")
            school = self.filter_form.cleaned_data.get("school")
            academic_year = self.filter_form.cleaned_data.get("academic_year")
            term = self.filter_form.cleaned_data.get("term")
            class_section = self.filter_form.cleaned_data.get("class_section")
            is_active = self.filter_form.cleaned_data.get("is_active")

            if query:
                queryset = queryset.filter(
                    Q(name__icontains=query)
                    | Q(description__icontains=query)
                    | Q(school__name__icontains=query)
                    | Q(class_section__grade_level__icontains=query)
                    | Q(class_section__stream__icontains=query)
                )
            if school:
                queryset = queryset.filter(school=school)
            if academic_year:
                queryset = queryset.filter(academic_year=academic_year)
            if term:
                queryset = queryset.filter(term=term)
            if class_section:
                queryset = queryset.filter(class_section=class_section)
            if is_active:
                queryset = queryset.filter(is_active=is_active == "true")

        return queryset


class FeeStructureCreateView(HtmxTemplateMixin, FinanceFormContextMixin, SuccessMessageFormMixin, FinanceAdminWriteMixin, CreateView):
    model = FeeStructure
    form_class = FeeStructureForm
    template_name = "finance/feestructure_form.html"
    htmx_template_name = "finance/partials/feestructure_form_modal.html"
    permission_required = "finance.add_feestructure"
    form_title = "Create fee structure"
    submit_label = "Create fee structure"
    list_url_name = "finance:feestructure-list"
    success_message = "Fee structure created successfully."

    def get_success_url(self):
        return reverse("finance:feestructure-list")


class FeeStructureUpdateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, FinanceFormContextMixin, SuccessMessageFormMixin, FinanceAdminWriteMixin, UpdateView):
    # FeeStructure has a direct school FK.
    school_lookup = "school_id"
    model = FeeStructure
    form_class = FeeStructureForm
    template_name = "finance/feestructure_form.html"
    htmx_template_name = "finance/partials/feestructure_form_modal.html"
    permission_required = "finance.change_feestructure"
    form_title = "Edit fee structure"
    submit_label = "Save changes"
    list_url_name = "finance:feestructure-list"
    success_message = "Fee structure updated successfully."

    def get_success_url(self):
        return reverse("finance:feestructure-list")


# ---------------------------------------------------------------------------
# Invoice views
# ---------------------------------------------------------------------------

class InvoiceListView(HtmxTemplateMixin, FinanceListContextMixin, FinanceReadMixin, ListView):
    model = Invoice
    template_name = "finance/invoice_list.html"
    htmx_template_name = "finance/partials/invoice_results.html"
    context_object_name = "invoices"
    paginate_by = 15
    page_title = "Invoices"
    create_url_name = "finance:invoice-create"
    permission_required = "finance.view_invoice"

    def get_queryset(self):
        self.filter_form = InvoiceFilterForm(self.request.GET or None)
        queryset = Invoice.objects.select_related(
            "enrollment__student__user",
            "enrollment__class_section",
            "enrollment__term",
            "enrollment__school",
            "fee_structure",
        ).prefetch_related(
            Prefetch(
                "payments",
                queryset=Payment.objects.filter(status=Payment.Status.SUCCESSFUL)
                .select_related("received_by")
                .order_by("-paid_at"),
                to_attr="successful_payments",
            )
        )

        # Parents see only their own children's invoices
        if self.request.user.role == User.Role.PARENT:
            student_ids = _parent_student_ids(self.request.user)
            queryset = queryset.filter(enrollment__student_id__in=student_ids)

        if self.filter_form.is_valid():
            query = self.filter_form.cleaned_data.get("q")
            status = self.filter_form.cleaned_data.get("status")
            term = self.filter_form.cleaned_data.get("term")
            class_section = self.filter_form.cleaned_data.get("class_section")

            if query:
                queryset = queryset.filter(
                    Q(invoice_number__icontains=query)
                    | Q(enrollment__student__admission_number__icontains=query)
                    | Q(enrollment__student__user__first_name__icontains=query)
                    | Q(enrollment__student__user__last_name__icontains=query)
                )
            if status:
                queryset = queryset.filter(status=status)
            if term:
                queryset = queryset.filter(enrollment__term=term)
            if class_section:
                queryset = queryset.filter(enrollment__class_section=class_section)

        return queryset


class InvoiceDetailView(FinanceReadMixin, DetailView):
    model = Invoice
    template_name = "finance/invoice_detail.html"
    context_object_name = "invoice"
    permission_required = "finance.view_invoice"

    def get_object(self, queryset=None):
        obj = get_object_or_404(
            Invoice.objects.select_related(
                "enrollment__student__user",
                "enrollment__class_section",
                "enrollment__term",
                "enrollment__school",
                "fee_structure",
            ).prefetch_related("payments__received_by"),
            pk=self.kwargs["pk"],
        )
        _enforce_parent_invoice_access(self.request.user, obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payments = self.object.payments.select_related("received_by").order_by("-paid_at")
        receipt_payments = payments.filter(status=Payment.Status.SUCCESSFUL)
        pending_payments = payments.filter(status=Payment.Status.PENDING)
        context["payments"] = payments
        context["receipt_payments"] = receipt_payments
        context["pending_payments"] = pending_payments
        context["last_successful_payment"] = receipt_payments.first()
        context["is_parent_finance_view"] = self.request.user.is_parent_role
        context["stk_enabled"] = settings.MPESA_STK_ENABLED
        context["can_initiate_stk"] = (
            self.request.user.is_parent_role
            and settings.MPESA_STK_ENABLED
            and self.object.balance > Decimal("0.00")
        )
        context["default_phone"] = self.request.user.phone or ""
        context["can_record_payment"] = (
            not self.request.user.is_parent_role
            and self.request.user.has_perm("finance.add_payment")
        )
        return context


class PaymentReceiptDownloadView(FinanceReadMixin, View):
    permission_required = "finance.view_payment"

    def get(self, request, *args, **kwargs):
        payment = get_object_or_404(
            Payment.objects.select_related(
                "invoice__enrollment__student__user",
                "invoice__enrollment__class_section",
                "invoice__enrollment__term",
                "invoice__fee_structure",
                "received_by",
            ),
            pk=kwargs["pk"],
        )
        if payment.status != Payment.Status.SUCCESSFUL:
            raise PermissionDenied
        _enforce_parent_invoice_access(request.user, payment.invoice)

        response = _pdf_response(f"receipt-{payment.reference_number}.pdf")
        rows = [
            ["Receipt reference", payment.reference_number],
            ["Invoice", payment.invoice.invoice_number],
            ["Student", payment.invoice.enrollment.student.user.get_full_name() or payment.invoice.enrollment.student.user.username],
            ["Admission No", payment.invoice.enrollment.student.admission_number],
            ["Fee item", payment.invoice.fee_structure.name],
            ["Class", payment.invoice.enrollment.class_section.display_name],
            ["Term", payment.invoice.enrollment.term.get_name_display()],
            ["Amount paid", f"KES {payment.amount}"],
            ["Balance after payment", f"KES {payment.invoice.balance}"],
            ["Payment date", payment.paid_at.strftime("%d %b %Y, %H:%M")],
            ["Method", payment.get_payment_method_display()],
            ["M-Pesa receipt", payment.mpesa_receipt_number or "-"],
            ["Received by", payment.received_by.get_full_name() if payment.received_by else "-"],
        ]
        _build_pdf_report(response, "School Fee Receipt", ["Field", "Value"], rows)
        return response


class InvoiceCreateView(HtmxTemplateMixin, FinanceFormContextMixin, SuccessMessageFormMixin, FinanceAdminWriteMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = "finance/invoice_form.html"
    htmx_template_name = "finance/partials/invoice_form_modal.html"
    permission_required = "finance.add_invoice"
    form_title = "Create invoice"
    submit_label = "Create invoice"
    list_url_name = "finance:invoice-list"
    success_message = "Invoice created successfully."

    def get_success_url(self):
        return reverse("finance:invoice-detail", kwargs={"pk": self.object.pk})


class InvoiceUpdateView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, FinanceFormContextMixin, SuccessMessageFormMixin, FinanceAdminWriteMixin, UpdateView):
    # Invoice -> enrollment (students.Enrollment) -> school
    school_lookup = "enrollment__school_id"
    model = Invoice
    form_class = InvoiceForm
    template_name = "finance/invoice_form.html"
    htmx_template_name = "finance/partials/invoice_form_modal.html"
    permission_required = "finance.change_invoice"
    form_title = "Edit invoice"
    submit_label = "Save changes"
    list_url_name = "finance:invoice-list"
    success_message = "Invoice updated successfully."

    def get_success_url(self):
        return reverse("finance:invoice-detail", kwargs={"pk": self.object.pk})


# ---------------------------------------------------------------------------
# Payment views
# ---------------------------------------------------------------------------

class PaymentCreateView(HtmxTemplateMixin, FinanceFormContextMixin, SuccessMessageFormMixin, FinanceAdminWriteMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = "finance/payment_form.html"
    htmx_template_name = "finance/partials/payment_form_modal.html"
    permission_required = "finance.add_payment"
    submit_label = "Record payment"
    list_url_name = "finance:invoice-list"
    success_message = "Payment recorded successfully."

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.invoice = get_object_or_404(
            Invoice.objects.select_related("enrollment__student__user", "fee_structure"),
            pk=self.kwargs["invoice_pk"],
        )

    def get_form_title(self):
        return f"Record payment — {self.invoice.invoice_number}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invoice"] = self.invoice
        context["form_title"] = self.get_form_title()
        context["cancel_url"] = reverse("finance:invoice-detail", kwargs={"pk": self.invoice.pk})
        return context

    def form_valid(self, form):
        form.instance.invoice = self.invoice
        response = super().form_valid(form)
        if self.object.status == Payment.Status.SUCCESSFUL and settings.SEND_PAYMENT_NOTIFICATIONS:
            send_payment_receipt_task.apply_async(args=[self.object.pk], queue="high", priority=9)
        return response

    def get_success_url(self):
        return reverse("finance:invoice-detail", kwargs={"pk": self.invoice.pk})


class FeeArrearListView(FinanceAdminTeacherReadMixin, ListView):
    model = FeeArrear
    template_name = "finance/fee_arrear_list.html"
    context_object_name = "arrears"
    paginate_by = 20
    permission_required = "finance.view_invoice"

    def get_queryset(self):
        queryset = FeeArrear.objects.select_related(
            "school",
            "student__user",
            "invoice__enrollment__class_section",
            "invoice__enrollment__term",
            "invoice__enrollment__school",
        ).order_by("-days_overdue", "-outstanding_amount")

        status = self.request.GET.get("status", "")
        class_section = self.request.GET.get("class_section", "")
        min_days_overdue = self.request.GET.get("min_days_overdue", "")
        q = self.request.GET.get("q", "").strip()

        if status:
            queryset = queryset.filter(status=status)
        if class_section:
            queryset = queryset.filter(invoice__enrollment__class_section_id=class_section)
        if min_days_overdue:
            queryset = queryset.filter(days_overdue__gte=min_days_overdue)
        if q:
            queryset = queryset.filter(
                Q(student__admission_number__icontains=q)
                | Q(student__user__first_name__icontains=q)
                | Q(student__user__last_name__icontains=q)
                | Q(invoice__invoice_number__icontains=q)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = FeeArrear.Status.choices
        context["total_outstanding"] = sum(item.outstanding_amount for item in context["arrears"])

        # Aging analytics – computed over the *unfiltered* school-scoped arrears
        active_statuses = [FeeArrear.Status.PENDING, FeeArrear.Status.OVERDUE]
        base_qs = FeeArrear.objects.filter(status__in=active_statuses, outstanding_amount__gt=0)
        if self.request.user.school_id:
            base_qs = base_qs.filter(school_id=self.request.user.school_id)
        context["aging_30"] = base_qs.filter(days_overdue__lte=30).aggregate(
            count=Count("pk"), total=Sum("outstanding_amount")
        )
        context["aging_60"] = base_qs.filter(days_overdue__gt=30, days_overdue__lte=60).aggregate(
            count=Count("pk"), total=Sum("outstanding_amount")
        )
        context["aging_90"] = base_qs.filter(days_overdue__gt=60, days_overdue__lte=90).aggregate(
            count=Count("pk"), total=Sum("outstanding_amount")
        )
        context["aging_90plus"] = base_qs.filter(days_overdue__gt=90).aggregate(
            count=Count("pk"), total=Sum("outstanding_amount")
        )
        return context


class ReminderPolicyUpdateView(FinanceAdminWriteMixin, View):
    permission_required = "finance.change_invoice"
    template_name = "finance/reminder_policy_form.html"

    def _resolve_school(self, request):
        if request.user.school_id:
            return request.user.school
        return School.objects.order_by("name").first()

    def get(self, request, *args, **kwargs):
        school = self._resolve_school(request)
        if not school:
            messages.warning(request, "No school found to configure reminder policy.")
            return HttpResponseRedirect(reverse("finance:fee-arrear-list"))

        policy = ReminderPolicy.get_for_school(school)
        form = ReminderPolicyForm(instance=policy)
        return self._render(request, form=form, school=school)

    def post(self, request, *args, **kwargs):
        school = self._resolve_school(request)
        if not school:
            messages.warning(request, "No school found to configure reminder policy.")
            return HttpResponseRedirect(reverse("finance:fee-arrear-list"))

        policy = ReminderPolicy.get_for_school(school)
        form = ReminderPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, "Reminder policy updated successfully.")
            return HttpResponseRedirect(reverse("finance:reminder-policy-update"))
        return self._render(request, form=form, school=school)

    def _render(self, request, *, form, school):
        htmx = getattr(request, "htmx", None)
        template = (
            "finance/partials/reminder_policy_form_modal.html"
            if htmx and not getattr(htmx, "boosted", False)
            else self.template_name
        )
        return render(
            request,
            template,
            {
                "form": form,
                "school": school,
                "form_title": "Reminder policy",
                "submit_label": "Save policy",
                "cancel_url": reverse("finance:fee-arrear-list"),
            },
        )


class FeeArrearExportCsvView(FinanceAdminTeacherReadMixin, View):
    permission_required = "finance.view_invoice"

    def get(self, request, *args, **kwargs):
        queryset = FeeArrear.objects.select_related(
            "student__user",
            "invoice__enrollment__class_section",
            "invoice__enrollment__term",
        ).order_by("-days_overdue", "-outstanding_amount")

        if getattr(request.user, "school_id", None):
            queryset = queryset.filter(school_id=request.user.school_id)

        limit = getattr(settings, "EXPORT_ROW_LIMIT", 5000)
        total_count = queryset.count()
        truncated = total_count > limit
        if truncated:
            queryset = queryset[:limit]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="fee-arrears.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Admission Number",
            "Student",
            "Invoice Number",
            "Class",
            "Term",
            "Outstanding",
            "Days Overdue",
            "Status",
            "Last Reminder",
        ])

        row_count = 0
        for arrear in queryset.iterator():
            writer.writerow([
                arrear.student.admission_number,
                arrear.student.user.get_full_name() or arrear.student.user.username,
                arrear.invoice.invoice_number,
                arrear.invoice.enrollment.class_section.display_name,
                arrear.invoice.enrollment.term,
                arrear.outstanding_amount,
                arrear.days_overdue,
                arrear.get_status_display(),
                arrear.last_reminder_sent_at.isoformat() if arrear.last_reminder_sent_at else "",
            ])
            row_count += 1

        if truncated:
            writer.writerow([])
            writer.writerow([f"Export limited to {limit} of {total_count} rows. Refine your filters."])

        return response


@method_decorator(login_required, name="dispatch")
class SendArrearReminderView(FinanceAdminWriteMixin, View):
    allowed_roles = (User.Role.SCHOOL_ADMIN,)
    permission_required = "finance.change_invoice"

    def post(self, request, *args, **kwargs):
        # Rate limit: 20 manual reminders per admin per minute
        client_ip = get_client_ip(request) or "unknown"
        rl_response = check_rate_limit(f"reminder-single:{request.user.id}:{client_ip}", limit=20, window=60)
        if rl_response:
            messages.warning(request, "Too many reminders sent. Please wait before sending more.")
            return HttpResponseRedirect(reverse("finance:fee-arrear-list"))

        arrear = get_object_or_404(FeeArrear, pk=kwargs["pk"])
        # Manual admin-triggered reminders bypass the throttle so the click always sends.
        sent = ReminderService.send_arrear_reminder(arrear, initiated_by=request.user, force=True)
        if sent:
            messages.success(request, "Reminder sent.")
        else:
            messages.warning(request, "Reminder skipped or failed.")
        return HttpResponseRedirect(reverse("finance:fee-arrear-list"))


@method_decorator(login_required, name="dispatch")
class SendBulkArrearReminderView(FinanceAdminWriteMixin, View):
    allowed_roles = (User.Role.SCHOOL_ADMIN,)
    permission_required = "finance.change_invoice"

    def post(self, request, *args, **kwargs):
        # Rate limit: 3 bulk sends per admin per 10 minutes
        client_ip = get_client_ip(request) or "unknown"
        rl_response = check_rate_limit(f"reminder-bulk:{request.user.id}:{client_ip}", limit=3, window=600)
        if rl_response:
            messages.warning(request, "Too many bulk reminder batches. Please wait before sending more.")
            return HttpResponseRedirect(reverse("finance:fee-arrear-list"))

        ids = request.POST.getlist("arrear_ids")
        queryset = FeeArrear.objects.filter(pk__in=ids).select_related(
            "student__user",
            "invoice__enrollment__student__user",
        )
        sent_count = 0
        for arrear in queryset:
            # Bulk admin clicks bypass the throttle so explicit operator action always sends.
            if ReminderService.send_arrear_reminder(arrear, initiated_by=request.user, force=True):
                sent_count += 1
        messages.success(request, f"Sent {sent_count} reminders.")
        return HttpResponseRedirect(reverse("finance:fee-arrear-list"))


class MpesaSTKPushInitView(FinanceReadMixin, View):
    permission_required = "finance.view_invoice"

    def post(self, request, *args, **kwargs):
        if not settings.MPESA_STK_ENABLED:
            return JsonResponse({"ok": False, "error": "M-Pesa payments are currently disabled."}, status=400)

        # Rate limit: 5 STK pushes per IP per minute to prevent cost abuse
        client_ip = get_client_ip(request) or "unknown"
        rl_response = check_rate_limit(f"mpesa-stk:{client_ip}", limit=5, window=60)
        if rl_response:
            return rl_response

        invoice = get_object_or_404(Invoice, pk=kwargs["invoice_pk"])
        _enforce_parent_invoice_access(request.user, invoice)

        if invoice.balance <= Decimal("0.00"):
            return JsonResponse({"ok": False, "error": "Invoice is already cleared."}, status=400)

        requested_amount = request.POST.get("amount", "").strip()
        try:
            amount = Decimal(requested_amount) if requested_amount else invoice.balance
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid amount."}, status=400)

        if amount <= Decimal("0.00") or amount > invoice.balance:
            return JsonResponse({"ok": False, "error": "Amount must be within invoice balance."}, status=400)

        phone_number = request.POST.get("phone_number", "").strip() or request.user.phone
        if not phone_number:
            return JsonResponse({"ok": False, "error": "Phone number is required."}, status=400)
        try:
            kenya_phone_validator(phone_number)
        except ValidationError:
            return JsonResponse({"ok": False, "error": "Invalid Kenyan phone number format."}, status=400)

        callback_url = request.build_absolute_uri(reverse("finance:mpesa-callback"))
        # Daraja cannot send custom headers, so we attach an HMAC-signed,
        # time-limited token as a query parameter.  The token expires after
        # 5 minutes so that logged URLs cannot be replayed.
        sep = "&" if "?" in callback_url else "?"
        callback_url = f"{callback_url}{sep}token={generate_callback_token()}"
        service = MpesaService()

        with transaction.atomic():
            # Lock the invoice row to prevent concurrent STK pushes
            Invoice.objects.select_for_update().get(pk=invoice.pk)

            existing_pending = Payment.objects.select_for_update().filter(
                invoice=invoice,
                status=Payment.Status.PENDING,
                payment_method=Payment.Method.MPESA,
                mpesa_phone_number=phone_number,
                created_at__gte=timezone.now() - timedelta(minutes=10),
            ).order_by("-created_at").first()
            if existing_pending and existing_pending.mpesa_checkout_request_id:
                _create_audit_log(
                    request=request,
                    actor=request.user,
                    object_repr=f"Invoice {invoice.invoice_number}",
                    metadata={
                        "event": "mpesa_stk_init_reused_pending",
                        "invoice_id": invoice.pk,
                        "payment_id": existing_pending.pk,
                        "checkout_request_id": existing_pending.mpesa_checkout_request_id,
                    },
                )
                return JsonResponse(
                    {
                        "ok": True,
                        "payment_id": existing_pending.pk,
                        "checkout_request_id": existing_pending.mpesa_checkout_request_id,
                        "message": "A previous STK request is still pending on your phone.",
                    }
                )

            payment = Payment.objects.create(
                invoice=invoice,
                amount=amount,
                payment_method=Payment.Method.MPESA,
                status=Payment.Status.PENDING,
                mpesa_phone_number=phone_number,
                notes="STK push initiated",
            )

            try:
                response = service.start_stk_push(
                    phone_number=phone_number,
                    amount=amount,
                    callback_url=callback_url,
                    account_reference=invoice.invoice_number,
                    transaction_desc="School fees",
                )
            except MpesaServiceError as exc:
                payment.status = Payment.Status.FAILED
                payment.notes = f"STK init failed: {exc}"
                payment.save(update_fields=["status", "notes", "updated_at"])
                _create_audit_log(
                    request=request,
                    actor=request.user,
                    object_repr=f"Invoice {invoice.invoice_number}",
                    metadata={
                        "event": "mpesa_stk_init_failed",
                        "invoice_id": invoice.pk,
                        "payment_id": payment.pk,
                        "error": str(exc),
                    },
                )
                return JsonResponse({"ok": False, "error": str(exc)}, status=400)

            payment.mpesa_checkout_request_id = response.get("CheckoutRequestID", "")
            payment.mpesa_transaction_id = response.get("MerchantRequestID", "")
            payment.notes = response.get("ResponseDescription", "STK request accepted")
            payment.save(update_fields=["mpesa_checkout_request_id", "mpesa_transaction_id", "notes", "updated_at"])

        _create_audit_log(
            request=request,
            actor=request.user,
            object_repr=f"Invoice {invoice.invoice_number}",
            metadata={
                "event": "mpesa_stk_init_success",
                "invoice_id": invoice.pk,
                "payment_id": payment.pk,
                "checkout_request_id": payment.mpesa_checkout_request_id,
            },
        )

        return JsonResponse(
            {
                "ok": True,
                "payment_id": payment.pk,
                "checkout_request_id": payment.mpesa_checkout_request_id,
                "message": payment.notes,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class MpesaCallbackView(View):
    # Reject payloads larger than 256 KB to prevent memory abuse
    MAX_PAYLOAD_BYTES = 256 * 1024

    def post(self, request, *args, **kwargs):
        # Accept either a legacy static token (header or query) or a new
        # HMAC-signed time-limited token (query only).  The HMAC path is
        # preferred because logged URLs cannot be replayed after expiry.
        provided_token = (
            request.headers.get("X-KSMS-CALLBACK-TOKEN", "")
            or request.GET.get("token", "")
        )
        legacy_token = getattr(settings, "MPESA_CALLBACK_TOKEN", "")
        # Default-deny: the callback is processed only when a legacy static
        # token or a valid HMAC token is presented.  A MISSING token is a
        # rejection, not a pass-through.  compare_digest runs on bytes because
        # str inputs with non-ASCII characters raise TypeError.
        legacy_ok = bool(legacy_token) and hmac.compare_digest(
            provided_token.encode("utf-8"), legacy_token.encode("utf-8")
        )
        hmac_ok = bool(provided_token) and validate_callback_token(provided_token)

        if not (legacy_ok or hmac_ok):
            _create_audit_log(
                request=request,
                actor=None,
                object_repr="M-Pesa callback",
                metadata={
                    "event": "mpesa_callback_unauthorized",
                    "remote_addr": get_client_ip(request),
                    "token_provided": bool(provided_token),
                },
            )
            return JsonResponse({"ok": False, "error": "Unauthorized or expired callback token."}, status=403)

        if not request.body:
            return JsonResponse({"ok": False, "error": "Callback payload is required."}, status=400)
        if len(request.body) > self.MAX_PAYLOAD_BYTES:
            return JsonResponse({"ok": False, "error": "Payload too large."}, status=400)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid callback payload."}, status=400)

        callback = payload.get("Body", {}).get("stkCallback")
        if not isinstance(callback, dict):
            return JsonResponse({"ok": False, "error": "Invalid callback structure."}, status=400)

        checkout_request_id = callback.get("CheckoutRequestID")
        if not checkout_request_id:
            return JsonResponse({"ok": False, "error": "Missing CheckoutRequestID."}, status=400)

        result_code = callback.get("ResultCode")
        result_desc = callback.get("ResultDesc", "")

        with transaction.atomic():
            payment = Payment.objects.select_for_update().select_related("invoice").filter(
                mpesa_checkout_request_id=checkout_request_id
            ).first()
            if not payment:
                return JsonResponse({"ok": True, "message": "No matching payment."})

            prior_status = payment.status
            payment.mpesa_result_code = result_code
            payment.mpesa_result_description = result_desc

            callback_success = int(result_code if result_code is not None else 1) == 0
            should_notify = False

            if callback_success:
                metadata = callback.get("CallbackMetadata", {}).get("Item", [])
                values = {item.get("Name"): item.get("Value") for item in metadata if isinstance(item, dict)}
                receipt_number = values.get("MpesaReceiptNumber", "")

                if prior_status == Payment.Status.SUCCESSFUL:
                    _create_audit_log(
                        request=request,
                        actor=None,
                        object_repr=f"Payment {payment.reference_number}",
                        metadata={
                            "event": "mpesa_callback_duplicate_success",
                            "payment_id": payment.pk,
                            "checkout_request_id": checkout_request_id,
                            "result_code": result_code,
                        },
                    )
                    return JsonResponse({"ok": True, "message": "Already processed."})

                if prior_status in {Payment.Status.FAILED, Payment.Status.REVERSED}:
                    _create_audit_log(
                        request=request,
                        actor=None,
                        object_repr=f"Payment {payment.reference_number}",
                        metadata={
                            "event": "mpesa_callback_conflict_after_terminal",
                            "payment_id": payment.pk,
                            "checkout_request_id": checkout_request_id,
                            "prior_status": prior_status,
                            "result_code": result_code,
                        },
                    )
                    return JsonResponse({"ok": True, "message": "Terminal state already set."})

                # KSMS-02: never let the callback body set the credited
                # amount.  On mismatch, record an audit row for a human and
                # answer 200 so Safaricom does not retry forever; the payment
                # stays untouched (not marked SUCCESSFUL).
                callback_amount = values.get("Amount")
                if callback_amount is not None:
                    try:
                        callback_amount = Decimal(str(callback_amount))
                    except (InvalidOperation, ValueError):
                        callback_amount = None
                    if callback_amount is None or callback_amount != payment.amount:
                        _create_audit_log(
                            request=request,
                            actor=None,
                            object_repr=f"Payment {payment.reference_number}",
                            metadata={
                                "event": "mpesa_callback_amount_mismatch",
                                "payment_id": payment.pk,
                                "expected": str(payment.amount),
                                "received": str(values.get("Amount")),
                            },
                        )
                        return JsonResponse({"ok": True, "message": "Amount mismatch recorded."})

                payment.status = Payment.Status.SUCCESSFUL
                payment.mpesa_receipt_number = receipt_number or payment.mpesa_receipt_number
                payment.mpesa_phone_number = str(values.get("PhoneNumber", payment.mpesa_phone_number or ""))
                payment.amount = Decimal(str(values.get("Amount", payment.amount)))
                payment.paid_at = timezone.now()
                should_notify = True
            else:
                if prior_status == Payment.Status.SUCCESSFUL:
                    _create_audit_log(
                        request=request,
                        actor=None,
                        object_repr=f"Payment {payment.reference_number}",
                        metadata={
                            "event": "mpesa_callback_ignored_failure_after_success",
                            "payment_id": payment.pk,
                            "checkout_request_id": checkout_request_id,
                            "result_code": result_code,
                        },
                    )
                    return JsonResponse({"ok": True, "message": "Payment already successful."})
                payment.status = Payment.Status.FAILED

            payment.save()

        _create_audit_log(
            request=request,
            actor=None,
            object_repr=f"Payment {payment.reference_number}",
            metadata={
                "event": "mpesa_callback_processed",
                "payment_id": payment.pk,
                "checkout_request_id": checkout_request_id,
                "result_code": result_code,
                "prior_status": prior_status,
                "final_status": payment.status,
            },
        )

        if should_notify and settings.SEND_PAYMENT_NOTIFICATIONS:
            send_payment_receipt_task.apply_async(args=[payment.pk], queue="high", priority=9)

        return JsonResponse({"ok": True})


class DeletedInvoiceListView(HtmxTemplateMixin, FinanceAdminWriteMixin, ListView):
    model = Invoice
    template_name = "finance/deleted_invoice_list.html"
    htmx_template_name = "finance/partials/deleted_invoice_results.html"
    context_object_name = "invoices"
    paginate_by = 15
    permission_required = "finance.view_invoice"

    def get_queryset(self):
        return Invoice.all_objects.deleted().select_related(
            "enrollment__student__user",
            "enrollment__class_section",
            "enrollment__term",
            "enrollment__school",
            "fee_structure",
        ).order_by("-deleted_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Deleted invoices"
        return context


class DeletedPaymentListView(SchoolScopedQuerysetMixin, HtmxTemplateMixin, FinanceAdminWriteMixin, ListView):
    model = Payment
    # Payment -> invoice (finance.Invoice) -> enrollment -> school
    school_lookup = "invoice__enrollment__school_id"
    template_name = "finance/deleted_payment_list.html"
    htmx_template_name = "finance/partials/deleted_payment_results.html"
    context_object_name = "payments"
    paginate_by = 15
    permission_required = "finance.view_payment"

    def get_unscoped_queryset(self):
        # Soft-deleted payments only. AllSoftDeleteManager has no .deleted()
        # shortcut (that helper exists on the students/ querysets only), so
        # filter on deleted_at directly — the previous
        # Payment.all_objects.deleted() call raised AttributeError (500).
        return Payment.all_objects.filter(deleted_at__isnull=False).select_related(
            "invoice__enrollment__student__user",
            "invoice__fee_structure",
            "received_by",
        ).order_by("-deleted_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Deleted payments"
        return context


class RestoreInvoiceView(FinanceAdminWriteMixin, View):
    permission_required = "finance.change_invoice"

    def post(self, request, *args, **kwargs):
        invoice = Invoice.all_objects.select_related("enrollment__student__user").get(pk=kwargs["pk"])
        invoice.deleted_at = None
        invoice.save(update_fields=["deleted_at", "updated_at"])
        messages.success(request, f"Invoice {invoice.invoice_number} restored successfully.")
        return HttpResponseRedirect(reverse("finance:invoice-detail", kwargs={"pk": invoice.pk}))


class RestorePaymentView(FinanceAdminWriteMixin, View):
    permission_required = "finance.change_payment"

    def post(self, request, *args, **kwargs):
        payment = Payment.all_objects.select_related("invoice").get(pk=kwargs["pk"])
        payment.deleted_at = None
        payment.save(update_fields=["deleted_at", "updated_at"])
        payment.invoice.refresh_financial_state()
        messages.success(request, f"Payment {payment.reference_number} restored successfully.")
        return HttpResponseRedirect(reverse("finance:invoice-detail", kwargs={"pk": payment.invoice.pk}))
