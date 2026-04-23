from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.dishes.services import import_dishes_csv


class Command(BaseCommand):
    help = "Import dishes from semicolon CSV."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        result = import_dishes_csv(path.read_text(encoding="utf-8-sig"), dry_run=options["dry_run"])
        prefix = "DRY RUN (no changes committed): " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}created={result.created} updated={result.updated} skipped={result.skipped} errors={len(result.errors or [])}"
            )
        )
        for item in result.errors or []:
            self.stdout.write(self.style.WARNING(f"row {item['row']}: {item['error']}"))
