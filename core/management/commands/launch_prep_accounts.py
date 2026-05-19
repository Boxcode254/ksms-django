from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from allauth.account.models import EmailAddress


class Command(BaseCommand):
    help = (
        "Prepare accounts for launch by deactivating or rotating demo accounts "
        "and enforcing creation/update of the final superuser with a fresh password."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--demo-usernames",
            default="",
            help="Comma-separated demo usernames. Defaults to DEMO_USERNAMES setting.",
        )
        parser.add_argument(
            "--demo-action",
            choices=["deactivate", "rotate"],
            required=True,
            help="How to handle demo accounts during launch prep.",
        )
        parser.add_argument(
            "--rotate-to-password",
            default="",
            help=(
                "Required when --demo-action=rotate. New password for demo accounts. "
                "Use a non-demo value if you plan to keep these accounts active."
            ),
        )
        parser.add_argument(
            "--final-username",
            default=getattr(settings, "FINAL_SUPERUSER_USERNAME", ""),
            help="Final launch superuser username.",
        )
        parser.add_argument(
            "--final-email",
            default=getattr(settings, "FINAL_SUPERUSER_EMAIL", ""),
            help="Final launch superuser email.",
        )
        parser.add_argument(
            "--final-password",
            default="",
            help="Fresh password for the final superuser (required).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report actions without writing changes.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if getattr(settings, "DEMO_MODE", False):
            raise CommandError("Launch prep cannot run while DEMO_MODE=True. Set DEMO_MODE=False first.")

        final_username = (options["final_username"] or "").strip()
        final_email = (options["final_email"] or "").strip().lower()
        final_password = options["final_password"]

        if not final_username:
            raise CommandError("Missing final superuser username. Use --final-username or FINAL_SUPERUSER_USERNAME.")
        if not final_email:
            raise CommandError("Missing final superuser email. Use --final-email or FINAL_SUPERUSER_EMAIL.")
        if not final_password:
            raise CommandError("Missing final superuser password. Use --final-password.")

        demo_default_password = getattr(settings, "DEMO_DEFAULT_PASSWORD", "ChangeMe12345")
        if final_password == demo_default_password:
            raise CommandError("Final superuser password must be fresh and cannot match demo default password.")

        action = options["demo_action"]
        rotate_to_password = options["rotate_to_password"]
        if action == "rotate":
            if not rotate_to_password:
                raise CommandError("--rotate-to-password is required when --demo-action=rotate.")
            if rotate_to_password == demo_default_password:
                raise CommandError("Rotation target password cannot be the demo default password.")

        demo_usernames_arg = options["demo_usernames"].strip()
        if demo_usernames_arg:
            demo_usernames = [item.strip() for item in demo_usernames_arg.split(",") if item.strip()]
        else:
            demo_usernames = list(getattr(settings, "DEMO_USERNAMES", []))

        if final_username in demo_usernames:
            demo_usernames = [u for u in demo_usernames if u != final_username]

        user_model = get_user_model()

        # Validate the final password using Django validators against a candidate user object.
        candidate_user = user_model(username=final_username, email=final_email)
        validate_password(final_password, user=candidate_user)

        demo_processed = 0
        missing_demo = []

        for username in demo_usernames:
            user = user_model.objects.filter(username=username).first()
            if not user:
                missing_demo.append(username)
                continue

            if options["dry_run"]:
                demo_processed += 1
                continue

            if action == "deactivate":
                user.is_active = False
                user.save(update_fields=["is_active"])
            else:
                user.set_password(rotate_to_password)
                user.save(update_fields=["password"])
            demo_processed += 1

        final_user = user_model.objects.filter(username=final_username).first()
        created_final = False

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run successful. No data changed."))
            self.stdout.write(
                f"Would process demo accounts: action={action}, count={demo_processed}, missing={len(missing_demo)}"
            )
            self.stdout.write(
                f"Would {'create' if final_user is None else 'update'} final superuser: {final_username}"
            )
            if missing_demo:
                self.stdout.write(self.style.WARNING("Missing demo users: " + ", ".join(missing_demo)))
            return

        if final_user is None:
            final_user = user_model.objects.create_superuser(
                username=final_username,
                email=final_email,
                password=final_password,
            )
            created_final = True
        else:
            if not final_user.is_superuser:
                raise CommandError(
                    f"Existing user '{final_username}' is not a superuser. Resolve manually before launch prep."
                )
            final_user.email = final_email
            final_user.set_password(final_password)
            final_user.is_active = True
            final_user.is_staff = True
            final_user.save(update_fields=["email", "password", "is_active", "is_staff"])

        EmailAddress.objects.filter(user=final_user).exclude(email=final_email).update(primary=False)
        EmailAddress.objects.update_or_create(
            user=final_user,
            email=final_email,
            defaults={"verified": True, "primary": True},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Launch prep complete: demo_processed={demo_processed}, missing_demo={len(missing_demo)}, "
                f"final_superuser={'created' if created_final else 'updated'}"
            )
        )
        if missing_demo:
            self.stdout.write(self.style.WARNING("Missing demo users: " + ", ".join(missing_demo)))
