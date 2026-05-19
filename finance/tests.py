import datetime
import json
from decimal import Decimal
from datetime import time
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicYear, ClassSection, Term
from core.models import School, User
from core.signals import sync_role_group_membership
from finance.models import FeeArrear, FeeStructure, Invoice, Payment, ReminderPolicy
from finance.forms import ReminderPolicyForm
from finance.services.notifications import ReminderService
from students.models import Enrollment, Guardian, Student, StudentGuardianRelationship


class FinanceModuleTestCase(TestCase):
    """Shared fixtures for all Module 4 Finance tests."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="KSMS Finance School",
            code="FINSCH",
            slug="ksms-finance-school",
            email="finance@testschool.example.com",
            phone="+254700000088",
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

        # Users
        cls.admin_user = User.objects.create_user(
            username="admin.finance",
            email="admin.finance@example.com",
            password="TestPass1234",
            role=User.Role.SCHOOL_ADMIN,
            first_name="Finance",
            last_name="Admin",
        )
        sync_role_group_membership(cls.admin_user)

        cls.teacher_user = User.objects.create_user(
            username="teacher.finance",
            email="teacher.finance@example.com",
            password="TestPass1234",
            role=User.Role.TEACHER,
            first_name="Finance",
            last_name="Teacher",
        )
        sync_role_group_membership(cls.teacher_user)

        cls.student_user = User.objects.create_user(
            username="student.finance",
            email="student.finance@example.com",
            password="TestPass1234",
            role=User.Role.STUDENT,
        )
        sync_role_group_membership(cls.student_user)

        cls.parent_user = User.objects.create_user(
            username="parent.finance",
            email="parent.finance@example.com",
            password="TestPass1234",
            role=User.Role.PARENT,
        )
        sync_role_group_membership(cls.parent_user)

        cls.other_parent_user = User.objects.create_user(
            username="parent.other.finance",
            email="parent.other.finance@example.com",
            password="TestPass1234",
            role=User.Role.PARENT,
        )
        sync_role_group_membership(cls.other_parent_user)

        # Student + guardian
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="FIN-001",
            admission_date=datetime.date(2026, 1, 9),
        )
        cls.guardian = Guardian.objects.create(
            school=cls.school,
            user=cls.parent_user,
        )
        cls.other_guardian = Guardian.objects.create(
            school=cls.school,
            user=cls.other_parent_user,
        )
        StudentGuardianRelationship.objects.create(
            student=cls.student,
            guardian=cls.guardian,
            relationship=StudentGuardianRelationship.Relationship.MOTHER,
            is_primary_contact=True,
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
        cls.fee_structure = FeeStructure.objects.create(
            school=cls.school,
            academic_year=cls.academic_year,
            term=cls.term,
            class_section=cls.section,
            name="Tuition Fee Term 1",
            amount=Decimal("15000.00"),
            due_date=datetime.date(2026, 2, 1),
            is_active=True,
        )
        cls.invoice = Invoice.objects.create(
            enrollment=cls.enrollment,
            fee_structure=cls.fee_structure,
            amount_due=Decimal("15000.00"),
            due_date=datetime.date(2026, 2, 1),
            status=Invoice.Status.PENDING,
        )

    def login(self, user):
        self.client.force_login(user)


# ---------------------------------------------------------------------------
# Permission / access tests
# ---------------------------------------------------------------------------

class FinancePermissionTests(FinanceModuleTestCase):

    def test_feestructure_list_requires_login(self):
        response = self.client.get(reverse("finance:feestructure-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response.url)

    def test_invoice_list_requires_login(self):
        response = self.client.get(reverse("finance:invoice-list"))
        self.assertEqual(response.status_code, 302)

    def test_invoice_detail_requires_login(self):
        response = self.client.get(reverse("finance:invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(response.status_code, 302)

    def test_admin_can_access_feestructure_list(self):
        self.login(self.admin_user)
        self.assertEqual(self.client.get(reverse("finance:feestructure-list")).status_code, 200)

    def test_teacher_denied_feestructure_list(self):
        self.login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("finance:feestructure-list")).status_code, 403)

    def test_teacher_denied_invoice_list(self):
        self.login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("finance:invoice-list")).status_code, 403)

    def test_parent_can_access_invoice_list(self):
        self.login(self.parent_user)
        self.assertEqual(self.client.get(reverse("finance:invoice-list")).status_code, 200)

    def test_student_denied_feestructure_list(self):
        self.login(self.student_user)
        self.assertEqual(self.client.get(reverse("finance:feestructure-list")).status_code, 403)

    def test_student_denied_invoice_list(self):
        self.login(self.student_user)
        self.assertEqual(self.client.get(reverse("finance:invoice-list")).status_code, 403)

    def test_teacher_denied_feestructure_create(self):
        self.login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("finance:feestructure-create")).status_code, 403)

    def test_teacher_denied_invoice_create(self):
        self.login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("finance:invoice-create")).status_code, 403)

    def test_teacher_denied_payment_create(self):
        self.login(self.teacher_user)
        self.assertEqual(
            self.client.get(reverse("finance:payment-create", args=[self.invoice.pk])).status_code,
            403,
        )

    def test_parent_denied_feestructure_create(self):
        self.login(self.parent_user)
        self.assertEqual(self.client.get(reverse("finance:feestructure-create")).status_code, 403)

    def test_admin_can_access_feestructure_create(self):
        self.login(self.admin_user)
        self.assertEqual(self.client.get(reverse("finance:feestructure-create")).status_code, 200)

    def test_admin_can_access_invoice_create(self):
        self.login(self.admin_user)
        self.assertEqual(self.client.get(reverse("finance:invoice-create")).status_code, 200)

    def test_admin_can_access_payment_create(self):
        self.login(self.admin_user)
        self.assertEqual(
            self.client.get(reverse("finance:payment-create", args=[self.invoice.pk])).status_code,
            200,
        )


# ---------------------------------------------------------------------------
# Admin write tests — FeeStructure and Invoice
# ---------------------------------------------------------------------------

class FinanceAdminWriteTests(FinanceModuleTestCase):

    def test_admin_can_create_fee_structure(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("finance:feestructure-create"),
            {
                "school": self.school.pk,
                "academic_year": self.academic_year.pk,
                "term": self.term.pk,
                "class_section": self.section.pk,
                "name": "Activity Fee Term 1",
                "description": "",
                "amount": "2000.00",
                "due_date": "2026-02-15",
                "is_active": True,
            },
        )
        self.assertRedirects(response, reverse("finance:feestructure-list"))
        self.assertTrue(
            FeeStructure.objects.filter(school=self.school, name="Activity Fee Term 1").exists()
        )

    def test_admin_can_update_fee_structure(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("finance:feestructure-update", args=[self.fee_structure.pk]),
            {
                "school": self.school.pk,
                "academic_year": self.academic_year.pk,
                "term": self.term.pk,
                "class_section": self.section.pk,
                "name": "Tuition Fee Term 1",
                "description": "Updated description",
                "amount": "15000.00",
                "due_date": "2026-02-01",
                "is_active": True,
            },
        )
        self.assertRedirects(response, reverse("finance:feestructure-list"))
        self.fee_structure.refresh_from_db()
        self.assertEqual(self.fee_structure.description, "Updated description")

    def test_admin_can_create_invoice(self):
        self.login(self.admin_user)
        # Create a second fee structure to avoid unique constraint on enrollment+fee_structure
        fee_structure2 = FeeStructure.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            term=self.term,
            class_section=self.section,
            name="Exam Fee Term 1",
            amount=Decimal("3000.00"),
            due_date=datetime.date(2026, 2, 1),
            is_active=True,
        )
        response = self.client.post(
            reverse("finance:invoice-create"),
            {
                "enrollment": self.enrollment.pk,
                "fee_structure": fee_structure2.pk,
                "amount_due": "3000.00",
                "due_date": "2026-02-01",
                "notes": "",
            },
        )
        new_invoice = Invoice.objects.filter(
            enrollment=self.enrollment, fee_structure=fee_structure2
        ).first()
        self.assertIsNotNone(new_invoice)
        self.assertRedirects(response, reverse("finance:invoice-detail", args=[new_invoice.pk]))

    def test_admin_can_update_invoice_notes(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("finance:invoice-update", args=[self.invoice.pk]),
            {
                "enrollment": self.enrollment.pk,
                "fee_structure": self.fee_structure.pk,
                "amount_due": "15000.00",
                "due_date": "2026-02-01",
                "notes": "Invoice updated via test",
            },
        )
        self.assertRedirects(response, reverse("finance:invoice-detail", args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.notes, "Invoice updated via test")


# ---------------------------------------------------------------------------
# Payment lifecycle tests
# ---------------------------------------------------------------------------

class FinancePaymentTests(FinanceModuleTestCase):

    def test_admin_can_record_partial_payment(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("finance:payment-create", args=[self.invoice.pk]),
            {
                "amount": "5000.00",
                "payment_method": Payment.Method.CASH,
                "status": Payment.Status.SUCCESSFUL,
                "paid_at": "2026-01-20T10:00",
                "received_by": "",
                "mpesa_receipt_number": "",
                "mpesa_phone_number": "",
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("finance:invoice-detail", args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("5000.00"))
        self.assertEqual(self.invoice.status, Invoice.Status.PARTIAL)

    def test_payment_transitions_invoice_to_paid(self):
        self.login(self.admin_user)
        # Reset state from previous test within the same DB transaction
        self.invoice.payments.all().delete()
        self.invoice.refresh_financial_state()

        self.client.post(
            reverse("finance:payment-create", args=[self.invoice.pk]),
            {
                "amount": "15000.00",
                "payment_method": Payment.Method.BANK,
                "status": Payment.Status.SUCCESSFUL,
                "paid_at": "2026-01-21T09:00",
                "received_by": "",
                "mpesa_receipt_number": "",
                "mpesa_phone_number": "",
                "notes": "",
            },
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(self.invoice.amount_paid, Decimal("15000.00"))
        self.assertEqual(self.invoice.balance, Decimal("0.00"))

    def test_payment_requires_mpesa_receipt_for_successful_mpesa(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("finance:payment-create", args=[self.invoice.pk]),
            {
                "amount": "1000.00",
                "payment_method": Payment.Method.MPESA,
                "status": Payment.Status.SUCCESSFUL,
                "paid_at": "2026-01-22T10:00",
                "received_by": "",
                "mpesa_receipt_number": "",  # Missing — should fail validation
                "mpesa_phone_number": "",
                "notes": "",
            },
        )
        # Form should be invalid and re-render
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Payment.objects.filter(invoice=self.invoice, payment_method=Payment.Method.MPESA).exists()
        )


# ---------------------------------------------------------------------------
# Parent access isolation tests
# ---------------------------------------------------------------------------

class FinanceParentAccessTests(FinanceModuleTestCase):

    def create_successful_payment(self):
        return Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("5000.00"),
            payment_method=Payment.Method.MPESA,
            status=Payment.Status.SUCCESSFUL,
            mpesa_receipt_number="QWE123RTY",
            mpesa_phone_number="+254700000111",
            received_by=self.admin_user,
        )

    def test_parent_sees_own_child_invoice_in_list(self):
        self.login(self.parent_user)
        response = self.client.get(reverse("finance:invoice-list"))
        self.assertEqual(response.status_code, 200)
        invoices = list(response.context["invoices"])
        self.assertIn(self.invoice, invoices)

    def test_other_parent_cannot_see_unrelated_invoice_in_list(self):
        self.login(self.other_parent_user)
        response = self.client.get(reverse("finance:invoice-list"))
        self.assertEqual(response.status_code, 200)
        invoices = list(response.context["invoices"])
        self.assertNotIn(self.invoice, invoices)

    def test_parent_can_view_own_child_invoice_detail(self):
        self.login(self.parent_user)
        response = self.client.get(reverse("finance:invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(response.status_code, 200)

    def test_parent_invoice_detail_shows_last_transaction_summary(self):
        payment = self.create_successful_payment()
        self.login(self.parent_user)
        response = self.client.get(reverse("finance:invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["last_successful_payment"], payment)
        self.assertContains(response, "Last transaction")
        self.assertContains(response, payment.reference_number)

    def test_other_parent_denied_invoice_detail(self):
        self.login(self.other_parent_user)
        response = self.client.get(reverse("finance:invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(response.status_code, 403)

    def test_parent_cannot_record_payment(self):
        self.login(self.parent_user)
        response = self.client.get(
            reverse("finance:payment-create", args=[self.invoice.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_parent_can_download_receipt_for_own_child_payment(self):
        payment = self.create_successful_payment()
        self.login(self.parent_user)
        response = self.client.get(reverse("finance:payment-receipt", args=[payment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f'receipt-{payment.reference_number}.pdf', response["Content-Disposition"])

    def test_other_parent_denied_receipt_for_unrelated_child_payment(self):
        payment = self.create_successful_payment()
        self.login(self.other_parent_user)
        response = self.client.get(reverse("finance:payment-receipt", args=[payment.pk]))
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------

class FinanceFilterTests(FinanceModuleTestCase):

    def test_feestructure_list_filter_by_school(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:feestructure-list"), {"school": self.school.pk}
        )
        self.assertEqual(response.status_code, 200)
        fee_structures = list(response.context["fee_structures"])
        self.assertIn(self.fee_structure, fee_structures)

    def test_feestructure_list_search_by_name(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:feestructure-list"), {"q": "Tuition"}
        )
        self.assertEqual(response.status_code, 200)
        fee_structures = list(response.context["fee_structures"])
        self.assertTrue(any(fs.name == "Tuition Fee Term 1" for fs in fee_structures))

    def test_feestructure_list_filter_active_only(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:feestructure-list"), {"is_active": "true"}
        )
        self.assertEqual(response.status_code, 200)
        for fs in response.context["fee_structures"]:
            self.assertTrue(fs.is_active)

    def test_invoice_list_filter_by_status(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:invoice-list"), {"status": Invoice.Status.PENDING}
        )
        self.assertEqual(response.status_code, 200)
        invoices = list(response.context["invoices"])
        self.assertIn(self.invoice, invoices)

    def test_invoice_list_filter_by_term(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:invoice-list"), {"term": self.term.pk}
        )
        self.assertEqual(response.status_code, 200)
        invoices = list(response.context["invoices"])
        self.assertIn(self.invoice, invoices)

    def test_invoice_list_search_by_invoice_number(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:invoice-list"),
            {"q": self.invoice.invoice_number[:10]},
        )
        self.assertEqual(response.status_code, 200)
        invoices = list(response.context["invoices"])
        self.assertIn(self.invoice, invoices)


# ---------------------------------------------------------------------------
# HTMX partial tests
# ---------------------------------------------------------------------------

class FinanceHtmxTests(FinanceModuleTestCase):

    def test_feestructure_list_htmx_returns_partial(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:feestructure-list"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/partials/feestructure_results.html")
        self.assertTemplateNotUsed(response, "base.html")

    def test_invoice_list_htmx_returns_partial(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:invoice-list"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/partials/invoice_results.html")
        self.assertTemplateNotUsed(response, "base.html")

    def test_invoice_list_boosted_htmx_returns_full_page(self):
        self.login(self.admin_user)
        response = self.client.get(
            reverse("finance:invoice-list"),
            HTTP_HX_REQUEST="true",
            HTTP_HX_BOOSTED="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/invoice_list.html")


class FeeArrearProjectionTests(FinanceModuleTestCase):

    def test_arrear_projection_created_from_invoice(self):
        arrear = FeeArrear.objects.filter(invoice=self.invoice).first()
        self.assertIsNotNone(arrear)
        self.assertEqual(arrear.outstanding_amount, self.invoice.balance)

    def test_arrear_projection_clears_after_full_payment(self):
        self.login(self.admin_user)
        self.client.post(
            reverse("finance:payment-create", args=[self.invoice.pk]),
            {
                "amount": "15000.00",
                "payment_method": Payment.Method.BANK,
                "status": Payment.Status.SUCCESSFUL,
                "paid_at": "2026-01-21T09:00",
                "received_by": "",
                "mpesa_receipt_number": "",
                "mpesa_phone_number": "",
                "notes": "",
            },
        )

        self.invoice.refresh_from_db()
        arrear = FeeArrear.objects.get(invoice=self.invoice)
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(arrear.status, FeeArrear.Status.CLEARED)
        self.assertEqual(arrear.outstanding_amount, Decimal("0.00"))


class FeeArrearEndpointTests(FinanceModuleTestCase):

    def test_admin_can_access_fee_arrear_list(self):
        self.login(self.admin_user)
        response = self.client.get(reverse("finance:fee-arrear-list"))
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_access_fee_arrear_list(self):
        self.login(self.parent_user)
        response = self.client.get(reverse("finance:fee-arrear-list"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_trigger_single_reminder(self):
        self.login(self.admin_user)
        arrear = FeeArrear.objects.get(invoice=self.invoice)
        response = self.client.post(reverse("finance:fee-arrear-remind", args=[arrear.pk]))
        self.assertEqual(response.status_code, 302)

    def test_admin_can_export_fee_arrears_csv(self):
        self.login(self.admin_user)
        response = self.client.get(reverse("finance:fee-arrear-export-csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("fee-arrears.csv", response["Content-Disposition"])


class MpesaFlowTests(FinanceModuleTestCase):

    @patch("finance.views.MpesaService.start_stk_push")
    def test_parent_can_initiate_stk_push(self, mock_start_stk_push):
        mock_start_stk_push.return_value = {
            "CheckoutRequestID": "ws_CO_123",
            "MerchantRequestID": "mr_123",
            "ResponseDescription": "Success. Request accepted for processing",
        }
        self.login(self.parent_user)

        with self.settings(MPESA_STK_ENABLED=True):
            response = self.client.post(
                reverse("finance:mpesa-stk-init", args=[self.invoice.pk]),
                {"amount": "1200", "phone_number": "+254700000088"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        payment = Payment.objects.get(pk=payload["payment_id"])
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.mpesa_checkout_request_id, "ws_CO_123")

    @patch("finance.views.MpesaService.start_stk_push")
    def test_stk_init_reuses_existing_pending_payment(self, mock_start_stk_push):
        mock_start_stk_push.return_value = {
            "CheckoutRequestID": "ws_CO_999",
            "MerchantRequestID": "mr_999",
            "ResponseDescription": "Success. Request accepted for processing",
        }
        self.login(self.parent_user)

        existing = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("1000.00"),
            payment_method=Payment.Method.MPESA,
            status=Payment.Status.PENDING,
            mpesa_phone_number="+254700000088",
            mpesa_checkout_request_id="ws_existing_1",
        )

        with self.settings(MPESA_STK_ENABLED=True):
            response = self.client.post(
                reverse("finance:mpesa-stk-init", args=[self.invoice.pk]),
                {"amount": "1000", "phone_number": "+254700000088"},
            )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["payment_id"], existing.pk)
        self.assertEqual(payload["checkout_request_id"], "ws_existing_1")
        mock_start_stk_push.assert_not_called()

    def test_mpesa_callback_is_idempotent_for_success(self):
        payment = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("1500.00"),
            payment_method=Payment.Method.MPESA,
            status=Payment.Status.PENDING,
            mpesa_phone_number="+254700000088",
            mpesa_checkout_request_id="ws_callback_1",
        )
        callback_payload = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": "ws_callback_1",
                    "ResultCode": 0,
                    "ResultDesc": "Success",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 1500},
                            {"Name": "MpesaReceiptNumber", "Value": "RCP123456"},
                            {"Name": "PhoneNumber", "Value": 254700000088},
                        ]
                    },
                }
            }
        }

        with self.settings(MPESA_CALLBACK_TOKEN=""):
            first = self.client.post(
                reverse("finance:mpesa-callback"),
                data=json.dumps(callback_payload),
                content_type="application/json",
            )
            second = self.client.post(
                reverse("finance:mpesa-callback"),
                data=json.dumps(callback_payload),
                content_type="application/json",
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
        self.assertEqual(payment.mpesa_receipt_number, "RCP123456")
        self.assertEqual(self.invoice.amount_paid, Decimal("1500.00"))

    def test_mpesa_callback_invalid_token_rejected(self):
        payload = {"Body": {"stkCallback": {"CheckoutRequestID": "x", "ResultCode": 1}}}
        with self.settings(MPESA_CALLBACK_TOKEN="secret-token"):
            response = self.client.post(
                reverse("finance:mpesa-callback"),
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_KSMS_CALLBACK_TOKEN="wrong-token",
            )
        self.assertEqual(response.status_code, 403)


class ReminderPolicyTests(FinanceModuleTestCase):

    def test_policy_is_created_with_defaults(self):
        policy = ReminderPolicy.get_for_school(self.school)
        self.assertEqual(policy.overdue_threshold_days, 10)
        self.assertEqual(policy.min_hours_between_sends, 24)

    def test_form_rejects_same_start_and_end_time(self):
        policy = ReminderPolicy.get_for_school(self.school)
        form = ReminderPolicyForm(
            data={
                "daily_enabled": True,
                "weekly_enabled": True,
                "overdue_threshold_days": 10,
                "min_hours_between_sends": 24,
                "send_window_start": "09:00",
                "send_window_end": "09:00",
            },
            instance=policy,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("cannot be the same", form.non_field_errors()[0])

    def test_form_rejects_partial_window_values(self):
        policy = ReminderPolicy.get_for_school(self.school)
        form = ReminderPolicyForm(
            data={
                "daily_enabled": True,
                "weekly_enabled": True,
                "overdue_threshold_days": 10,
                "min_hours_between_sends": 24,
                "send_window_start": "09:00",
                "send_window_end": "",
            },
            instance=policy,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("both send window", form.non_field_errors()[0])

    def test_form_rejects_end_before_start(self):
        policy = ReminderPolicy.get_for_school(self.school)
        form = ReminderPolicyForm(
            data={
                "daily_enabled": True,
                "weekly_enabled": True,
                "overdue_threshold_days": 10,
                "min_hours_between_sends": 24,
                "send_window_start": "16:00",
                "send_window_end": "09:00",
            },
            instance=policy,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("later than start", form.non_field_errors()[0])

    def test_send_window_boundaries_are_inclusive(self):
        policy = ReminderPolicy.get_for_school(self.school)
        policy.send_window_start = time(9, 0)
        policy.send_window_end = time(17, 0)

        with patch("finance.services.notifications.timezone.localtime") as mocked_localtime:
            mocked_localtime.return_value = datetime.datetime(2026, 1, 10, 9, 0)
            self.assertTrue(ReminderService.is_within_send_window(policy))

            mocked_localtime.return_value = datetime.datetime(2026, 1, 10, 17, 0)
            self.assertTrue(ReminderService.is_within_send_window(policy))

            mocked_localtime.return_value = datetime.datetime(2026, 1, 10, 8, 59)
            self.assertFalse(ReminderService.is_within_send_window(policy))

            mocked_localtime.return_value = datetime.datetime(2026, 1, 10, 17, 1)
            self.assertFalse(ReminderService.is_within_send_window(policy))


class ReminderPolicyViewTests(FinanceModuleTestCase):

    def test_admin_can_open_policy_screen(self):
        self.login(self.admin_user)
        response = self.client.get(reverse("finance:reminder-policy-update"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/reminder_policy_form.html")

    def test_parent_cannot_open_policy_screen(self):
        self.login(self.parent_user)
        response = self.client.get(reverse("finance:reminder-policy-update"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_update_policy_window(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("finance:reminder-policy-update"),
            {
                "daily_enabled": True,
                "weekly_enabled": False,
                "overdue_threshold_days": 14,
                "min_hours_between_sends": 36,
                "send_window_start": "09:00",
                "send_window_end": "16:30",
            },
        )
        self.assertEqual(response.status_code, 302)

        policy = ReminderPolicy.get_for_school(self.school)
        self.assertFalse(policy.weekly_enabled)
        self.assertEqual(policy.overdue_threshold_days, 14)
        self.assertEqual(policy.min_hours_between_sends, 36)
        self.assertEqual(policy.send_window_start, time(9, 0))
        self.assertEqual(policy.send_window_end, time(16, 30))

    def test_invalid_same_time_window_shows_form_error(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse("finance:reminder-policy-update"),
            {
                "daily_enabled": True,
                "weekly_enabled": True,
                "overdue_threshold_days": 10,
                "min_hours_between_sends": 24,
                "send_window_start": "10:00",
                "send_window_end": "10:00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot be the same time")


# ---------------------------------------------------------------------------
# Reminder service: message template, throttling, manual override, channel pref
# ---------------------------------------------------------------------------

class ReminderServiceMessageTests(FinanceModuleTestCase):

    def setUp(self):
        super().setUp()
        self.arrear = FeeArrear.objects.get(invoice=self.invoice)

    def test_build_message_includes_student_class_and_paybill(self):
        with self.settings(MPESA_SHORTCODE="247247"):
            msg = ReminderService.build_message(self.arrear)
        self.assertIn(self.student.user.get_full_name(), msg)
        self.assertIn(self.section.display_name, msg)
        self.assertIn("KES", msg)
        self.assertIn(str(self.arrear.outstanding_amount), msg)
        self.assertIn("Paybill 247247", msg)
        self.assertIn(self.invoice.invoice_number, msg)

    def test_build_message_omits_paybill_when_unconfigured(self):
        with self.settings(MPESA_SHORTCODE=""):
            msg = ReminderService.build_message(self.arrear)
        self.assertNotIn("Paybill", msg)


class ReminderServiceThrottleTests(FinanceModuleTestCase):

    def setUp(self):
        super().setUp()
        self.guardian.user.phone = "+254700000111"
        self.guardian.user.save(update_fields=["phone"])
        self.arrear = FeeArrear.objects.get(invoice=self.invoice)

    @patch("finance.services.notifications.ReminderService.send_sms")
    def test_automated_reminder_is_throttled_within_min_hours(self, mock_send):
        mock_send.return_value = (True, "msg-1", "")
        # First send should go through.
        sent_first = ReminderService.send_arrear_reminder(self.arrear)
        self.assertTrue(sent_first)
        self.assertEqual(mock_send.call_count, 1)

        # Second send within throttle window must be skipped (force=False).
        mock_send.reset_mock()
        sent_second = ReminderService.send_arrear_reminder(self.arrear)
        self.assertFalse(sent_second)
        mock_send.assert_not_called()

    @patch("finance.services.notifications.ReminderService.send_sms")
    def test_manual_admin_reminder_bypasses_throttle(self, mock_send):
        mock_send.return_value = (True, "msg-2", "")
        # Pretend we recently sent a reminder.
        self.arrear.last_reminder_sent_at = timezone.now()
        self.arrear.save(update_fields=["last_reminder_sent_at"])

        self.login(self.admin_user)
        response = self.client.post(reverse("finance:fee-arrear-remind", args=[self.arrear.pk]))
        self.assertEqual(response.status_code, 302)
        # The view passes force=True, so send_sms must be called despite recent send.
        self.assertEqual(mock_send.call_count, 1)

    @patch("finance.services.notifications.ReminderService.send_sms")
    def test_fee_payer_guardian_preferred_over_primary_contact(self, mock_send):
        mock_send.return_value = (True, "msg-3", "")
        # Promote the *other* guardian to fee payer for this student.
        self.other_guardian.user.phone = "+254700000999"
        self.other_guardian.user.save(update_fields=["phone"])
        StudentGuardianRelationship.objects.create(
            student=self.student,
            guardian=self.other_guardian,
            relationship=StudentGuardianRelationship.Relationship.FATHER,
            is_fee_payer=True,
        )

        ReminderService.send_arrear_reminder(self.arrear)
        # Must send to the fee payer's phone, not the primary contact's.
        called_phones = [call.args[0] for call in mock_send.call_args_list]
        self.assertEqual(called_phones, ["+254700000999"])


# ---------------------------------------------------------------------------
# CSV export school scoping
# ---------------------------------------------------------------------------

class FeeArrearCsvScopingTests(FinanceModuleTestCase):

    def setUp(self):
        super().setUp()
        # A second school with its own arrear that must not leak into the export.
        self.other_school = School.objects.create(
            name="Other School",
            code="OTHSCH",
            slug="other-school",
            email="other@example.com",
            phone="+254700000077",
            county="Nairobi",
        )
        other_year = AcademicYear.objects.create(
            school=self.other_school,
            name="2026",
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 11, 20),
            is_current=True,
        )
        other_term = Term.objects.create(
            school=self.other_school,
            academic_year=other_year,
            name=Term.Name.TERM_1,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 4, 10),
            is_current=True,
        )
        other_section = ClassSection.objects.create(
            school=self.other_school,
            academic_year=other_year,
            grade_level="Form 1",
            stream="B",
            capacity=40,
        )
        other_student_user = User.objects.create_user(
            username="student.other.finance",
            email="student.other.finance@example.com",
            password="TestPass1234",
            role=User.Role.STUDENT,
        )
        other_student = Student.objects.create(
            school=self.other_school,
            user=other_student_user,
            admission_number="OTH-001",
            admission_date=datetime.date(2026, 1, 9),
        )
        other_enrollment = Enrollment.objects.create(
            school=self.other_school,
            student=other_student,
            academic_year=other_year,
            term=other_term,
            class_section=other_section,
            status=Enrollment.Status.ACTIVE,
            start_date=other_term.start_date,
        )
        other_fee = FeeStructure.objects.create(
            school=self.other_school,
            academic_year=other_year,
            term=other_term,
            class_section=other_section,
            name="Tuition Fee Term 1",
            amount=Decimal("9000.00"),
            due_date=datetime.date(2026, 2, 1),
            is_active=True,
        )
        self.other_invoice = Invoice.objects.create(
            enrollment=other_enrollment,
            fee_structure=other_fee,
            amount_due=Decimal("9000.00"),
            due_date=datetime.date(2026, 2, 1),
            status=Invoice.Status.PENDING,
        )

        # Bind the test admin to the primary school so scoping kicks in.
        self.admin_user.school = self.school
        self.admin_user.save(update_fields=["school"])

    def test_csv_export_excludes_other_schools_arrears(self):
        self.login(self.admin_user)
        response = self.client.get(reverse("finance:fee-arrear-export-csv"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn(self.invoice.invoice_number, body)
        self.assertNotIn(self.other_invoice.invoice_number, body)


# ---------------------------------------------------------------------------
# Bulk reminder view
# ---------------------------------------------------------------------------

class BulkReminderViewTests(FinanceModuleTestCase):

    def setUp(self):
        super().setUp()
        self.guardian.user.phone = "+254700000111"
        self.guardian.user.save(update_fields=["phone"])

    @patch("finance.services.notifications.ReminderService.send_sms")
    def test_bulk_reminder_sends_to_each_selected_arrear(self, mock_send):
        mock_send.return_value = (True, "bulk-1", "")
        self.login(self.admin_user)
        arrear = FeeArrear.objects.get(invoice=self.invoice)
        response = self.client.post(
            reverse("finance:fee-arrear-remind-bulk"),
            {"arrear_ids": [arrear.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_send.call_count, 1)

    def test_parent_cannot_send_bulk_reminders(self):
        self.login(self.parent_user)
        response = self.client.post(reverse("finance:fee-arrear-remind-bulk"), {"arrear_ids": []})
        self.assertEqual(response.status_code, 403)
