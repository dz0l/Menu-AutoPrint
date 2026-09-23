from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.integrations.auth import generate_api_key, hash_api_key


class Command(BaseCommand):
    help = (
        "Create or update the integration service user and print a new API key. "
        "Store INTEGRATION_API_KEY_HASH and INTEGRATION_SERVICE_USER_ID in .env; "
        "the raw key is shown once."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="integration-service",
            help="Username for the service account",
        )
        parser.add_argument(
            "--print-env",
            action="store_true",
            help="Print suggested .env lines (includes raw key once)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        username = (options["username"] or "").strip()
        if not username:
            raise CommandError("username required")

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "role": User.Role.ADMIN,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
                "must_change_password": False,
            },
        )
        user.role = User.Role.ADMIN
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.must_change_password = False
        if created:
            user.set_unusable_password()
        user.save()

        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)

        self.stdout.write(self.style.SUCCESS(f"Service user id={user.id} username={user.username}"))
        self.stdout.write("Put these values into the server .env (raw key is shown once):")
        self.stdout.write(f"INTEGRATION_API_ENABLED=1")
        self.stdout.write(f"INTEGRATION_SERVICE_USER_ID={user.id}")
        self.stdout.write(f"INTEGRATION_API_KEY_HASH={key_hash}")
        self.stdout.write(f"# raw key for the client only: {raw_key}")
        if options["print_env"]:
            self.stdout.write("")
            self.stdout.write("Client credential (keep secret):")
            self.stdout.write(raw_key)

        if settings.INTEGRATION_API_KEY_HASH and settings.INTEGRATION_API_KEY_HASH != key_hash:
            self.stdout.write(
                self.style.WARNING(
                    "A different INTEGRATION_API_KEY_HASH is already set in the environment. "
                    "Replace it with the new hash above to activate this key."
                )
            )
