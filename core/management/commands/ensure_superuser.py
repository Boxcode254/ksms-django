"""
Non-interactive superuser creation for Railway / container deployments.

Reads DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, and
DJANGO_SUPERUSER_PASSWORD from the environment.  Creates the superuser
only if it does not already exist.  Safe to run on every container start.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from allauth.account.models import EmailAddress


class Command(BaseCommand):
    help = "Create superuser from env vars if it does not already exist (non-interactive, idempotent)."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "").strip()

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    "Skipping superuser creation: DJANGO_SUPERUSER_USERNAME "
                    "and/or DJANGO_SUPERUSER_PASSWORD not set."
                )
            )
            return

        if User.objects.filter(username=username).exists():
            user = User.objects.get(username=username)
            # Ensure the existing user is actually a superuser
            if not user.is_superuser:
                self.stdout.write(
                    self.style.WARNING(
                        f"User '{username}' exists but is NOT a superuser. "
                        "Refusing to modify. Resolve manually."
                    )
                )
                return
            self.stdout.write(
                self.style.SUCCESS(f"Superuser '{username}' already exists. No action needed.")
            )
            return

        user = User.objects.create_superuser(
            username=username,
            email=email or f"{username}@ksms.local",
            password=password,
        )

        # Mark the email as verified in allauth so the user can log in
        # immediately without an email confirmation round-trip.
        if email:
            EmailAddress.objects.update_or_create(
                user=user,
                email=email,
                defaults={"verified": True, "primary": True},
            )

        self.stdout.write(
            self.style.SUCCESS(f"Superuser '{username}' created successfully.")
        )
