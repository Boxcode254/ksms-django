from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import School, TimeStampedModel
from core.validators import (
	document_upload_validators,
	kenya_phone_validator,
	mpesa_code_validator,
	non_negative_money_validator,
	positive_money_validator,
)


def generate_invoice_number(school):
	prefix = school.code.upper() if school and school.code else "KSMS"
	return f"INV-{prefix}-{timezone.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"


def generate_payment_reference():
	return f"PAY-{timezone.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"


class SoftDeleteQuerySet(models.QuerySet):
	def delete(self):
		return self.update(deleted_at=timezone.now())

	def active(self):
		return self.filter(deleted_at__isnull=True)

	def deleted(self):
		return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
	def get_queryset(self):
		return SoftDeleteQuerySet(self.model, using=self._db).active()


class AllSoftDeleteManager(models.Manager):
	def get_queryset(self):
		return SoftDeleteQuerySet(self.model, using=self._db)


class FeeStructure(TimeStampedModel):
	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fee_structures")
	academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="fee_structures")
	term = models.ForeignKey("academics.Term", on_delete=models.PROTECT, related_name="fee_structures")
	class_section = models.ForeignKey("academics.ClassSection", on_delete=models.PROTECT, related_name="fee_structures")
	name = models.CharField(max_length=120)
	description = models.TextField(blank=True)
	amount = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		validators=[positive_money_validator],
	)
	due_date = models.DateField()
	supporting_document = models.FileField(
		upload_to="finance/fee-structures/",
		blank=True,
		null=True,
		validators=document_upload_validators,
	)
	is_active = models.BooleanField(default=True, db_index=True)

	class Meta:
		ordering = ("school_id", "term_id", "class_section_id", "name")
		constraints = [
			models.UniqueConstraint(
				fields=("school", "term", "class_section", "name"),
				name="finance_unique_fee_structure_per_class_term",
			),
		]
		indexes = [
			models.Index(fields=("school", "term", "is_active")),
			models.Index(fields=("school", "academic_year", "is_active")),
			models.Index(fields=("school", "due_date")),
		]
		verbose_name = "Fee structure"
		verbose_name_plural = "Fee structures"

	def clean(self):
		errors = {}
		if self.academic_year_id and self.school_id and self.academic_year.school_id != self.school_id:
			errors["academic_year"] = "Academic year must belong to the selected school."
		if self.term_id and self.school_id and self.term.school_id != self.school_id:
			errors["term"] = "Term must belong to the selected school."
		if self.class_section_id and self.school_id and self.class_section.school_id != self.school_id:
			errors["class_section"] = "Class section must belong to the selected school."
		if self.term_id and self.academic_year_id and self.term.academic_year_id != self.academic_year_id:
			errors["term"] = "Term must belong to the selected academic year."
		if self.class_section_id and self.academic_year_id and self.class_section.academic_year_id != self.academic_year_id:
			errors["class_section"] = "Class section must belong to the selected academic year."
		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"{self.name} - {self.class_section.display_name}"


class Invoice(TimeStampedModel):
	class Status(models.TextChoices):
		DRAFT = "draft", "Draft"
		PENDING = "pending", "Pending"
		PARTIAL = "partial", "Partial"
		PAID = "paid", "Paid"
		OVERDUE = "overdue", "Overdue"
		CANCELLED = "cancelled", "Cancelled"

	enrollment = models.ForeignKey("students.Enrollment", on_delete=models.PROTECT, related_name="invoices")
	fee_structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT, related_name="invoices")
	invoice_number = models.CharField(max_length=40, unique=True, blank=True, editable=False)
	issued_date = models.DateField(default=timezone.localdate, db_index=True)
	due_date = models.DateField(blank=True, null=True)
	amount_due = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		validators=[positive_money_validator],
	)
	amount_paid = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		default=Decimal("0.00"),
		validators=[non_negative_money_validator],
	)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
	invoice_document = models.FileField(
		upload_to="finance/invoices/",
		blank=True,
		null=True,
		validators=document_upload_validators,
	)
	notes = models.TextField(blank=True)
	deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

	class Meta:
		ordering = ("-issued_date", "invoice_number")
		constraints = [
			models.UniqueConstraint(
				fields=("enrollment", "fee_structure"),
				name="finance_unique_invoice_per_enrollment_fee_structure",
			),
		]
		indexes = [
			models.Index(fields=("status", "due_date")),
			models.Index(fields=("enrollment", "issued_date")),
			models.Index(fields=("enrollment", "status"), name="fin_inv_enr_status_idx"),
		]
		verbose_name = "Invoice"
		verbose_name_plural = "Invoices"

	objects = SoftDeleteManager()
	all_objects = AllSoftDeleteManager()

	@property
	def is_deleted(self):
		return self.deleted_at is not None

	@property
	def balance(self):
		return self.amount_due - self.amount_paid

	def clean(self):
		errors = {}
		if self.enrollment_id and self.fee_structure_id:
			if self.enrollment.school_id != self.fee_structure.school_id:
				errors["fee_structure"] = "Fee structure must belong to the same school as the enrollment."
			if self.enrollment.term_id != self.fee_structure.term_id:
				errors["fee_structure"] = "Fee structure term must match the enrollment term."
			if self.enrollment.class_section_id != self.fee_structure.class_section_id:
				errors["fee_structure"] = "Fee structure class section must match the enrollment class section."
		if self.amount_paid and self.amount_paid < Decimal("0.00"):
			errors["amount_paid"] = "Amount paid cannot be negative."
		if errors:
			raise ValidationError(errors)

	def save(self, *args, sync_arrears=True, **kwargs):
		if not self.invoice_number:
			self.invoice_number = generate_invoice_number(self.enrollment.school if self.enrollment_id else None)
		if not self.due_date and self.fee_structure_id:
			self.due_date = self.fee_structure.due_date
		super().save(*args, **kwargs)
		if self.pk and sync_arrears:
			FeeArrear.sync_from_invoice(self)

	def refresh_financial_state(self, commit=True):
		total_paid = self.payments.filter(status=Payment.Status.SUCCESSFUL).aggregate(total=Sum("amount"))["total"]
		self.amount_paid = total_paid or Decimal("0.00")

		if self.status != self.Status.CANCELLED:
			if self.amount_paid >= self.amount_due:
				self.status = self.Status.PAID
			elif self.amount_paid > Decimal("0.00"):
				self.status = self.Status.PARTIAL
			elif self.due_date and self.due_date < timezone.localdate():
				self.status = self.Status.OVERDUE
			else:
				self.status = self.Status.PENDING

		if commit:
			self.save(update_fields=["amount_paid", "status", "updated_at"])

	def delete(self, *args, **kwargs):
		self.deleted_at = timezone.now()
		self.save(update_fields=["deleted_at", "updated_at"])

	def __str__(self):
		return f"{self.invoice_number} - {self.enrollment.student}"


class Payment(TimeStampedModel):
	class Method(models.TextChoices):
		MPESA = "mpesa", "M-Pesa"
		BANK = "bank", "Bank"
		CASH = "cash", "Cash"
		CHEQUE = "cheque", "Cheque"

	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		SUCCESSFUL = "successful", "Successful"
		FAILED = "failed", "Failed"
		REVERSED = "reversed", "Reversed"

	invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
	amount = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		validators=[positive_money_validator],
	)
	payment_method = models.CharField(max_length=20, choices=Method.choices, db_index=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESSFUL, db_index=True)
	reference_number = models.CharField(max_length=40, unique=True, blank=True)
	paid_at = models.DateTimeField(default=timezone.now, db_index=True)
	received_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="received_payments",
	)
	notes = models.TextField(blank=True)
	proof_document = models.FileField(
		upload_to="finance/payment-proofs/",
		blank=True,
		null=True,
		validators=document_upload_validators,
	)
	mpesa_receipt_number = models.CharField(
		max_length=20,
		blank=True,
		null=True,
		unique=True,
		validators=[mpesa_code_validator],
	)
	mpesa_transaction_id = models.CharField(max_length=50, blank=True)
	mpesa_checkout_request_id = models.CharField(max_length=100, blank=True)
	# Phone encryption deferred to post-MVP.
	mpesa_phone_number = models.CharField(
		max_length=16,
		blank=True,
		validators=[kenya_phone_validator],
	)
	mpesa_payer_name = models.CharField(max_length=255, blank=True)
	mpesa_result_code = models.PositiveIntegerField(blank=True, null=True)
	mpesa_result_description = models.CharField(max_length=255, blank=True)
	deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

	class Meta:
		ordering = ("-paid_at", "-created_at")
		indexes = [
			models.Index(fields=("invoice", "status", "-paid_at")),
			models.Index(fields=("payment_method", "status", "-paid_at")),
			models.Index(fields=("mpesa_checkout_request_id",)),
		]
		verbose_name = "Payment"
		verbose_name_plural = "Payments"

	objects = SoftDeleteManager()
	all_objects = AllSoftDeleteManager()

	@property
	def is_deleted(self):
		return self.deleted_at is not None

	def clean(self):
		errors = {}
		if self.payment_method == self.Method.MPESA and self.status == self.Status.SUCCESSFUL and not self.mpesa_receipt_number:
			errors["mpesa_receipt_number"] = "Successful M-Pesa payments require an M-Pesa receipt number."

		if self.status == self.Status.SUCCESSFUL and self.invoice_id:
			successful_payments = self.invoice.payments.filter(status=self.Status.SUCCESSFUL).exclude(pk=self.pk)
			total_paid = successful_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
			if total_paid + self.amount > self.invoice.amount_due:
				errors["amount"] = "Payment amount cannot exceed the remaining invoice balance."

		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		if not self.reference_number:
			self.reference_number = self.mpesa_receipt_number or generate_payment_reference()
		super().save(*args, **kwargs)
		self.invoice.refresh_financial_state()

	def delete(self, *args, **kwargs):
		invoice = self.invoice
		self.deleted_at = timezone.now()
		self.save(update_fields=["deleted_at", "updated_at"])
		invoice.refresh_financial_state()

	def __str__(self):
		return f"{self.reference_number} - {self.invoice.invoice_number}"


class FeeArrear(TimeStampedModel):
	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		OVERDUE = "overdue", "Overdue"
		CLEARED = "cleared", "Cleared"

	school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fee_arrears")
	student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="fee_arrears")
	invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="arrear_projection")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
	amount_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[non_negative_money_validator])
	amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[non_negative_money_validator])
	outstanding_amount = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		default=Decimal("0.00"),
		validators=[non_negative_money_validator],
	)
	due_date = models.DateField(blank=True, null=True, db_index=True)
	days_overdue = models.PositiveIntegerField(default=0, db_index=True)
	last_reminder_sent_at = models.DateTimeField(blank=True, null=True)
	last_reminder_channel = models.CharField(max_length=20, blank=True)
	reminder_count = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ("-days_overdue", "-outstanding_amount", "due_date")
		indexes = [
			models.Index(fields=("school", "status", "due_date")),
			models.Index(fields=("school", "days_overdue", "status")),
			models.Index(fields=("student", "status")),
		]
		verbose_name = "Fee arrear"
		verbose_name_plural = "Fee arrears"

	@classmethod
	def sync_from_invoice(cls, invoice):
		if not invoice.enrollment_id:
			return None

		today = timezone.localdate()
		outstanding = max(invoice.balance, Decimal("0.00"))
		days_overdue = 0
		if invoice.due_date and outstanding > Decimal("0.00") and invoice.due_date < today:
			days_overdue = (today - invoice.due_date).days

		if outstanding <= Decimal("0.00"):
			status = cls.Status.CLEARED
		elif days_overdue > 0:
			status = cls.Status.OVERDUE
		else:
			status = cls.Status.PENDING

		arrear, _ = cls.objects.get_or_create(
			invoice=invoice,
			defaults={
				"school": invoice.enrollment.school,
				"student": invoice.enrollment.student,
			},
		)
		arrear.school = invoice.enrollment.school
		arrear.student = invoice.enrollment.student
		arrear.amount_due = invoice.amount_due
		arrear.amount_paid = invoice.amount_paid
		arrear.outstanding_amount = outstanding
		arrear.due_date = invoice.due_date
		arrear.days_overdue = days_overdue
		arrear.status = status
		arrear.save(
			update_fields=[
				"school",
				"student",
				"amount_due",
				"amount_paid",
				"outstanding_amount",
				"due_date",
				"days_overdue",
				"status",
				"updated_at",
			]
		)
		return arrear

	@classmethod
	def sync_all(cls, queryset=None):
		invoices = queryset or Invoice.objects.select_related("enrollment__school", "enrollment__student")
		for invoice in invoices.iterator():
			cls.sync_from_invoice(invoice)

	def __str__(self):
		return f"{self.student} - {self.outstanding_amount}"


class ReminderLog(TimeStampedModel):
	class Channel(models.TextChoices):
		SMS = "sms", "SMS"
		EMAIL = "email", "Email"
		MANUAL = "manual", "Manual"

	class Status(models.TextChoices):
		SENT = "sent", "Sent"
		FAILED = "failed", "Failed"

	arrear = models.ForeignKey(FeeArrear, on_delete=models.CASCADE, related_name="reminder_logs")
	channel = models.CharField(max_length=20, choices=Channel.choices)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
	message = models.TextField(blank=True)
	provider_reference = models.CharField(max_length=100, blank=True)
	error_message = models.TextField(blank=True)
	initiated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="fee_reminders_sent",
	)
	sent_at = models.DateTimeField(default=timezone.now, db_index=True)

	class Meta:
		ordering = ("-sent_at",)
		indexes = [
			models.Index(fields=("channel", "status", "sent_at")),
			models.Index(fields=("arrear", "sent_at")),
		]

	def __str__(self):
		return f"{self.get_channel_display()} - {self.arrear_id}"


class ReminderPolicy(TimeStampedModel):
	school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="fee_reminder_policy")
	daily_enabled = models.BooleanField(default=True)
	weekly_enabled = models.BooleanField(default=True)
	email_enabled = models.BooleanField(default=False, help_text="Also send reminders and receipts by email to guardians.")
	overdue_threshold_days = models.PositiveIntegerField(default=10)
	min_hours_between_sends = models.PositiveIntegerField(default=24)
	send_window_start = models.TimeField(blank=True, null=True)
	send_window_end = models.TimeField(blank=True, null=True)

	class Meta:
		verbose_name = "Reminder policy"
		verbose_name_plural = "Reminder policies"

	@classmethod
	def get_for_school(cls, school):
		policy, _ = cls.objects.get_or_create(school=school)
		return policy

	def __str__(self):
		return f"Reminder policy - {self.school.name}"
