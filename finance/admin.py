from django.contrib import admin

from .models import FeeArrear, FeeStructure, Invoice, Payment, ReminderLog, ReminderPolicy


@admin.action(description="Activate selected fee structures")
def activate_fee_structures(modeladmin, request, queryset):
	queryset.update(is_active=True)


@admin.action(description="Deactivate selected fee structures")
def deactivate_fee_structures(modeladmin, request, queryset):
	queryset.update(is_active=False)


@admin.action(description="Recalculate selected invoice balances and statuses")
def recalculate_invoice_statuses(modeladmin, request, queryset):
	for invoice in queryset:
		invoice.refresh_financial_state()


@admin.action(description="Mark selected invoices as cancelled")
def mark_invoices_cancelled(modeladmin, request, queryset):
	queryset.update(status=Invoice.Status.CANCELLED)


@admin.action(description="Mark selected payments as successful")
def mark_payments_successful(modeladmin, request, queryset):
	for payment in queryset.select_related("invoice"):
		payment.status = Payment.Status.SUCCESSFUL
		payment.save(update_fields=["status", "updated_at"])


@admin.action(description="Mark selected payments as failed")
def mark_payments_failed(modeladmin, request, queryset):
	for payment in queryset.select_related("invoice"):
		payment.status = Payment.Status.FAILED
		payment.save(update_fields=["status", "updated_at"])


class PaymentInline(admin.TabularInline):
	model = Payment
	extra = 0
	fields = ("paid_at", "amount", "payment_method", "status", "reference_number", "mpesa_receipt_number", "received_by")
	readonly_fields = ("reference_number",)
	autocomplete_fields = ("received_by",)
	show_change_link = True


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
	list_display = ("name", "school", "term", "class_section", "amount", "due_date", "is_active")
	list_filter = ("school", "academic_year", "term", "is_active")
	search_fields = ("name", "school__name", "class_section__grade_level", "class_section__stream")
	autocomplete_fields = ("school", "academic_year", "term", "class_section")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("school", "academic_year", "term", "class_section")
	ordering = ("school", "term", "class_section", "name")
	actions = (activate_fee_structures, deactivate_fee_structures)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
	list_display = ("invoice_number", "student_name", "fee_structure", "amount_due", "amount_paid", "balance_display", "status", "due_date")
	list_filter = ("status", "issued_date", "due_date", "fee_structure__school", "fee_structure__term")
	search_fields = (
		"invoice_number",
		"enrollment__student__admission_number",
		"enrollment__student__user__first_name",
		"enrollment__student__user__last_name",
		"fee_structure__name",
	)
	autocomplete_fields = ("enrollment", "fee_structure")
	readonly_fields = ("invoice_number", "amount_paid", "balance_display", "created_at", "updated_at")
	inlines = (PaymentInline,)
	list_select_related = ("enrollment__student__user", "fee_structure", "fee_structure__class_section")
	ordering = ("-issued_date", "invoice_number")
	date_hierarchy = "issued_date"
	actions = (recalculate_invoice_statuses, mark_invoices_cancelled)

	@admin.display(ordering="enrollment__student__admission_number", description="Student")
	def student_name(self, obj):
		return str(obj.enrollment.student)

	@admin.display(description="Balance")
	def balance_display(self, obj):
		return obj.balance


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
	list_display = ("paid_at", "invoice_number", "student_name", "amount", "payment_method", "status", "reference_number", "mpesa_receipt_number")
	list_filter = ("payment_method", "status", "paid_at", "invoice__fee_structure__school")
	search_fields = (
		"reference_number",
		"mpesa_receipt_number",
		"mpesa_checkout_request_id",
		"mpesa_phone_number",
		"invoice__invoice_number",
		"invoice__enrollment__student__admission_number",
		"invoice__enrollment__student__user__first_name",
		"invoice__enrollment__student__user__last_name",
	)
	autocomplete_fields = ("invoice", "received_by")
	readonly_fields = ("reference_number", "created_at", "updated_at")
	list_select_related = ("invoice__enrollment__student__user", "received_by")
	ordering = ("-paid_at",)
	date_hierarchy = "paid_at"
	actions = (mark_payments_successful, mark_payments_failed)

	@admin.display(ordering="invoice__invoice_number", description="Invoice")
	def invoice_number(self, obj):
		return obj.invoice.invoice_number

	@admin.display(ordering="invoice__enrollment__student__admission_number", description="Student")
	def student_name(self, obj):
		return str(obj.invoice.enrollment.student)


@admin.register(FeeArrear)
class FeeArrearAdmin(admin.ModelAdmin):
	list_display = (
		"student",
		"invoice",
		"status",
		"outstanding_amount",
		"days_overdue",
		"last_reminder_sent_at",
	)
	list_filter = ("status", "school", "days_overdue")
	search_fields = (
		"invoice__invoice_number",
		"student__admission_number",
		"student__user__first_name",
		"student__user__last_name",
	)
	autocomplete_fields = ("school", "student", "invoice")
	readonly_fields = ("created_at", "updated_at")
	ordering = ("-days_overdue", "-outstanding_amount")


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
	list_display = ("sent_at", "arrear", "channel", "status", "provider_reference", "initiated_by")
	list_filter = ("channel", "status", "sent_at")
	search_fields = ("arrear__invoice__invoice_number", "provider_reference", "error_message")
	autocomplete_fields = ("arrear", "initiated_by")
	readonly_fields = ("created_at", "updated_at", "sent_at")
	ordering = ("-sent_at",)


@admin.register(ReminderPolicy)
class ReminderPolicyAdmin(admin.ModelAdmin):
	list_display = (
		"school",
		"daily_enabled",
		"weekly_enabled",
		"overdue_threshold_days",
		"min_hours_between_sends",
	)
	search_fields = ("school__name", "school__code")
	autocomplete_fields = ("school",)
