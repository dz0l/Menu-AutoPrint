from django.core.management.base import BaseCommand

from apps.menu.archive import purge_old_archives, retention_days


class Command(BaseCommand):
    help = "Delete menu PDF archive entries older than the retention period (default 730 days)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override retention days (default from MENU_ARCHIVE_RETENTION_DAYS).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        removed = purge_old_archives(days=days)
        effective = days if days is not None else retention_days()
        self.stdout.write(self.style.SUCCESS(f"Purged {removed} archive entr(y/ies) older than {effective} days."))
