from datetime import timedelta

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from finance.models import ReminderLog, ReminderPolicy
from students.models import StudentGuardianRelationship


class ReminderService:
    @staticmethod
    def build_message(arrear):
        student_name = arrear.student.user.get_full_name() or arrear.student.user.username
        due_date = arrear.due_date.strftime("%d %b %Y") if arrear.due_date else "N/A"

        class_label = ""
        invoice = getattr(arrear, "invoice", None)
        enrollment = getattr(invoice, "enrollment", None) if invoice else None
        class_section = getattr(enrollment, "class_section", None) if enrollment else None
        if class_section is not None:
            class_label = f" ({class_section.display_name})"

        paybill = getattr(settings, "MPESA_SHORTCODE", "") or ""
        invoice_ref = invoice.invoice_number if invoice else ""

        message = (
            f"Dear Parent of {student_name}{class_label}, fee balance is KES {arrear.outstanding_amount}. "
            f"Please pay by {due_date}."
        )
        if paybill:
            account_ref = invoice_ref or "school fees"
            message += f" Pay via M-Pesa Paybill {paybill}, account {account_ref}."
        message += " — KSMS"
        return message

    @staticmethod
    def recently_reminded(arrear, policy):
        if not arrear.last_reminder_sent_at:
            return False
        return arrear.last_reminder_sent_at >= timezone.now() - timedelta(hours=policy.min_hours_between_sends)

    @staticmethod
    def is_within_send_window(policy):
        if not policy.send_window_start or not policy.send_window_end:
            return True
        now_t = timezone.localtime().time()
        return policy.send_window_start <= now_t <= policy.send_window_end

    @staticmethod
    def send_receipt_email(*, email, student_name, amount, receipt_ref, paid_at, balance, school_name):
        subject = f"KSMS Payment Receipt – KES {amount}"
        context = {
            "student_name": student_name,
            "amount": amount,
            "receipt_ref": receipt_ref,
            "paid_at": paid_at,
            "balance": balance,
            "school_name": school_name,
        }
        text_body = render_to_string("emails/payment_receipt.txt", context)
        html_body = render_to_string("emails/payment_receipt.html", context)
        try:
            msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [email])
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=True)
            return True
        except Exception:
            return False

    @staticmethod
    def send_reminder_email(*, email, student_name, outstanding_amount, due_date, school_name, is_overdue=False):
        subject = f"KSMS Fee Reminder – KES {outstanding_amount} Outstanding"
        context = {
            "student_name": student_name,
            "outstanding_amount": outstanding_amount,
            "due_date": due_date,
            "school_name": school_name,
            "is_overdue": is_overdue,
        }
        text_body = render_to_string("emails/fee_reminder.txt", context)
        html_body = render_to_string("emails/fee_reminder.html", context)
        try:
            msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [email])
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=True)
            return True
        except Exception:
            return False

    @classmethod
    def send_receipt_notification(cls, payment):
        """Send an SMS (and optional email) receipt to the paying guardian after a successful payment."""
        invoice = payment.invoice
        student = invoice.enrollment.student
        student_name = student.user.get_full_name() or student.user.username
        school_name = invoice.enrollment.school.name
        receipt_ref = payment.mpesa_receipt_number or payment.reference_number
        paid_at = payment.paid_at.strftime("%d %b %Y, %H:%M") if payment.paid_at else ""
        balance = invoice.balance

        sms_message = (
            f"KSMS Receipt: KES {payment.amount} received for {student_name}. "
            f"Ref: {receipt_ref}. Date: {paid_at}. "
            f"Balance: KES {balance}. Thank you – {school_name}."
        )

        guardians = StudentGuardianRelationship.objects.select_related("guardian__user").filter(
            student=student, is_fee_payer=True,
        )
        if not guardians.exists():
            guardians = StudentGuardianRelationship.objects.select_related("guardian__user").filter(
                student=student, is_primary_contact=True,
            )

        policy = ReminderPolicy.get_for_school(invoice.enrollment.school)
        sent_any = False
        for relation in guardians:
            phone = relation.guardian.user.phone
            if phone:
                ok, _, _ = cls.send_sms(phone, sms_message)
                if ok:
                    sent_any = True
            if policy.email_enabled:
                email_addr = relation.guardian.user.email
                if email_addr:
                    cls.send_receipt_email(
                        email=email_addr,
                        student_name=student_name,
                        amount=payment.amount,
                        receipt_ref=receipt_ref,
                        paid_at=paid_at,
                        balance=balance,
                        school_name=school_name,
                    )

        # Fallback: send to the M-Pesa phone number if no guardian found
        if not guardians.exists() and payment.mpesa_phone_number:
            ok, _, _ = cls.send_sms(payment.mpesa_phone_number, sms_message)
            if ok:
                sent_any = True

        return sent_any

    @staticmethod
    def send_sms(phone_number, message):
        if not settings.AFRICASTALKING_ENABLED:
            return False, "sms-disabled", "Africa's Talking is disabled"

        headers = {
            "apiKey": settings.AFRICASTALKING_API_KEY,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        payload = {
            "username": settings.AFRICASTALKING_USERNAME,
            "to": phone_number,
            "message": message,
        }
        if settings.AFRICASTALKING_SENDER_ID:
            payload["from"] = settings.AFRICASTALKING_SENDER_ID

        try:
            response = requests.post(
                settings.AFRICASTALKING_BASE_URL,
                data=payload,
                headers=headers,
                timeout=settings.AFRICASTALKING_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            body = response.json()
            recipients = body.get("SMSMessageData", {}).get("Recipients", [])
            provider_ref = recipients[0].get("messageId") if recipients else ""
            return True, provider_ref, ""
        except Exception as exc:  # pragma: no cover
            return False, "", str(exc)

    @classmethod
    def send_arrear_reminder(cls, arrear, initiated_by=None, force=False):
        policy = ReminderPolicy.get_for_school(arrear.school)
        if not cls.is_within_send_window(policy):
            return False
        if not force and cls.recently_reminded(arrear, policy):
            return False

        guardians = StudentGuardianRelationship.objects.select_related("guardian__user").filter(
            student=arrear.student,
            is_fee_payer=True,
        )
        if not guardians.exists():
            guardians = StudentGuardianRelationship.objects.select_related("guardian__user").filter(
                student=arrear.student,
                is_primary_contact=True,
            )

        message = cls.build_message(arrear)
        if arrear.days_overdue >= policy.overdue_threshold_days:
            message += " This account is significantly overdue and needs urgent clearance."
        sent_any = False
        for relation in guardians:
            phone = relation.guardian.user.phone
            if not phone:
                continue
            ok, provider_reference, error_message = cls.send_sms(phone, message)
            ReminderLog.objects.create(
                arrear=arrear,
                channel=ReminderLog.Channel.SMS,
                status=ReminderLog.Status.SENT if ok else ReminderLog.Status.FAILED,
                message=message,
                provider_reference=provider_reference,
                error_message=error_message,
                initiated_by=initiated_by,
            )
            if ok:
                sent_any = True

        if sent_any:
            arrear.last_reminder_sent_at = timezone.now()
            arrear.last_reminder_channel = ReminderLog.Channel.SMS
            arrear.reminder_count += 1
            arrear.save(update_fields=["last_reminder_sent_at", "last_reminder_channel", "reminder_count", "updated_at"])

        # Email reminders (if enabled on policy)
        if policy.email_enabled:
            due_date_str = arrear.due_date.strftime("%d %b %Y") if arrear.due_date else "N/A"
            is_overdue = arrear.days_overdue >= policy.overdue_threshold_days
            for relation in guardians:
                email_addr = relation.guardian.user.email
                if not email_addr:
                    continue
                school_name = arrear.school.name
                email_ok = cls.send_reminder_email(
                    email=email_addr,
                    student_name=arrear.student.user.get_full_name() or arrear.student.user.username,
                    outstanding_amount=arrear.outstanding_amount,
                    due_date=due_date_str,
                    school_name=school_name,
                    is_overdue=is_overdue,
                )
                ReminderLog.objects.create(
                    arrear=arrear,
                    channel=ReminderLog.Channel.EMAIL,
                    status=ReminderLog.Status.SENT if email_ok else ReminderLog.Status.FAILED,
                    message=message,
                    provider_reference="",
                    error_message="" if email_ok else "Email send failed",
                    initiated_by=initiated_by,
                )

        return sent_any
