from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update bootstrap editor account."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="mAdmin")
        parser.add_argument("--password", default="qwerty123")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        password = options["password"]
        user, created = User.objects.get_or_create(username=username, defaults={"is_staff": True, "is_superuser": True})
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.must_change_password = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(("Created" if created else "Updated") + f" bootstrap editor {username}"))
