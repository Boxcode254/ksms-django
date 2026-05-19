import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.models import School

from .models import FeeArrear, ReminderPolicy
from .services.notifications import ReminderService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=240,
    expires=3600,
    queue="default",
)
def sync_fee_arrears_task(self):
    if not settings.ARREARS_ENABLED:
        return 0
    try:
        FeeArrear.sync_all()
        return FeeArrear.objects.count()
    except Exception as exc:
        logger.exception("sync_fee_arrears_task failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    time_limit=600,
    soft_time_limit=480,
    expires=7200,
    queue="normal",
    priority=5,
)
def send_daily_fee_reminders_task(self):
    if not settings.AUTO_REMINDERS_ENABLED or not settings.REMINDER_DAILY_ENABLED:
        return 0

    sent = 0
    try:
        for school in School.objects.filter(is_active=True).iterator():
            policy = ReminderPolicy.get_for_school(school)
            if not policy.daily_enabled:
                continue

            queryset = FeeArrear.objects.select_related("student__user").filter(
                school=school,
                status__in=[FeeArrear.Status.PENDING, FeeArrear.Status.OVERDUE],
                outstanding_amount__gt=0,
            )

            for arrear in queryset.iterator():
                if ReminderService.send_arrear_reminder(arrear):
                    sent += 1
    except Exception as exc:
        logger.exception("send_daily_fee_reminders_task failed")
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))
    return sent


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=180,
    time_limit=600,
    soft_time_limit=480,
    expires=7200,
    queue="normal",
    priority=5,
)
def send_weekly_fee_reminders_task(self):
    if not settings.AUTO_REMINDERS_ENABLED or not settings.REMINDER_WEEKLY_ENABLED:
        return 0

    sent = 0
    try:
        for school in School.objects.filter(is_active=True).iterator():
            policy = ReminderPolicy.get_for_school(school)
            if not policy.weekly_enabled:
                continue

            queryset = FeeArrear.objects.select_related("student__user").filter(
                school=school,
                status=FeeArrear.Status.OVERDUE,
                days_overdue__gte=policy.overdue_threshold_days,
                outstanding_amount__gt=0,
            )

            for arrear in queryset.iterator():
                if ReminderService.send_arrear_reminder(arrear, force=True):
                    sent += 1
    except Exception as exc:
        logger.exception("send_weekly_fee_reminders_task failed")
        raise self.retry(exc=exc, countdown=180 * (2 ** self.request.retries))
    return sent


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    time_limit=60,
    soft_time_limit=45,
    expires=1800,
    queue="high",
    priority=9,
    acks_late=True,
)
def send_payment_receipt_task(self, payment_id):
    if not settings.SEND_PAYMENT_NOTIFICATIONS:
        return False

    from .models import Payment

    try:
        payment = (
            Payment.objects
            .select_related(
                "invoice__enrollment__student__user",
                "invoice__enrollment__school",
                "invoice__enrollment__class_section",
                "invoice__enrollment__term",
                "invoice__fee_structure",
            )
            .filter(pk=payment_id)
            .first()
        )
        if not payment or payment.status != Payment.Status.SUCCESSFUL:
            return False

        return ReminderService.send_receipt_notification(payment)
    except Exception as exc:
        logger.exception("send_payment_receipt_task failed for payment_id=%s", payment_id)
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
