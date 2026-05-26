import getpass
import os
import sys

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


PASSWORD_ENV = "MENU_AUTOPRINT_NEW_USER_PASSWORD"


class Command(BaseCommand):
    help = (
        "Create a user with admin or user role. Password is read from hidden TTY prompts "
        f"or {PASSWORD_ENV} for non-interactive runs."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", type=str)
        parser.add_argument(
            "--role",
            choices=["admin", "user"],
            default="user",
            help="admin: manages users; user: editor workflow",
        )
        parser.add_argument("--email", type=str, default="", help="Optional email")
        parser.add_argument("--update", action="store_true", help="Update an existing user's password and role")

    def _read_password(self) -> str:
        env_password = os.environ.get(PASSWORD_ENV)
        if env_password is not None:
            if not env_password:
                raise CommandError(f"{PASSWORD_ENV} is set but empty.")
            return env_password

        if sys.stdin.isatty():
            password = getpass.getpass("Password (hidden): ")
            password_repeat = getpass.getpass("Password (again): ")
            if password != password_repeat:
                raise CommandError("Passwords do not match.")
            if not password:
                raise CommandError("Password must not be empty.")
            return password

        raise CommandError(
            f"Non-interactive session: set {PASSWORD_ENV}, or run with a TTY, e.g. "
            "`docker compose exec -it web python manage.py create_staff_user mAdmin --role admin`."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"].strip()
        email = (options.get("email") or "").strip()
        role = options["role"]
        update_existing = options["update"]
        password = self._read_password()

        if not username:
            raise CommandError("Username must not be empty.")

        user = User.objects.filter(username=username).first()
        created = user is None
        if user and not update_existing:
            raise CommandError(f"User {username!r} already exists. Use --update to change it.")

        if created:
            user = User(username=username, email=email)
        elif email:
            user.email = email

        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        user.role = User.Role.ADMIN if role == "admin" else User.Role.USER
        user.is_staff = role == "admin"
        user.is_superuser = role == "admin"
        user.is_active = True
        user.must_change_password = False
        user.set_password(password)
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} user {username} ({role})."))
