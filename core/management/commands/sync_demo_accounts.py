from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from allauth.account.models import EmailAddress


class Command(BaseCommand):
    help = (
        "Synchronize demo accounts by setting a shared demo password and "
        "marking their emails as verified in allauth."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--usernames",
            default="",
            help="Comma-separated usernames to process. Defaults to DEMO_USERNAMES setting.",
        )
        parser.add_argument(
            "--password",
            default=getattr(settings, "DEMO_DEFAULT_PASSWORD", "ChangeMe12345"),
            help="Password to set for all targeted demo users.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        usernames_arg = options["usernames"].strip()
        if usernames_arg:
            usernames = [item.strip() for item in usernames_arg.split(",") if item.strip()]
        else:
            usernames = list(getattr(settings, "DEMO_USERNAMES", []))

        if not usernames:
            raise CommandError(
                "No demo usernames were provided. Use --usernames or set DEMO_USERNAMES in environment."
            )

        password = options["password"]
        user_model = get_user_model()

        processed = 0
        verified = 0
        missing_users = []
        missing_email = []

        for username in usernames:
            user = user_model.objects.filter(username=username).first()
            if not user:
                missing_users.append(username)
                continue

            user.set_password(password)
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["password", "is_active"])
            else:
                user.save(update_fields=["password"])
            processed += 1

            if not user.email:
                missing_email.append(username)
                continue

            # Keep exactly one primary address per user.
            EmailAddress.objects.filter(user=user).exclude(email=user.email).update(primary=False)
            _, _ = EmailAddress.objects.update_or_create(
                user=user,
                email=user.email,
                defaults={"verified": True, "primary": True},
            )
            verified += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo sync complete: processed={processed}, email_verified={verified}, missing={len(missing_users)}"
            )
        )

        if missing_users:
            self.stdout.write(self.style.WARNING("Missing users: " + ", ".join(missing_users)))

        if missing_email:
            self.stdout.write(
                self.style.WARNING(
                    "Users without email (verification skipped): " + ", ".join(missing_email)
                )
            )
