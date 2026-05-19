from django.core.management.base import BaseCommand

from finance.models import FeeArrear


class Command(BaseCommand):
    help = "Recompute fee arrears projection from invoices."

    def handle(self, *args, **options):
        FeeArrear.sync_all()
        self.stdout.write(self.style.SUCCESS(f"Synced {FeeArrear.objects.count()} arrear rows."))
