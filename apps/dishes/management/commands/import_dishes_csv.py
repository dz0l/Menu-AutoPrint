from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.dishes.services import import_dishes_csv_safely, replace_dishes_csv, review_dishes_csv_import


class Command(BaseCommand):
    help = "Safely import dishes from semicolon CSV."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--apply-updates", action="store_true")
        parser.add_argument(
            "--replace-all",
            action="store_true",
            help="Delete all current dishes and recreate the dishes table contents from CSV in one transaction.",
        )
        parser.add_argument("--show", type=int, default=20, help="How many review rows to print per section")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        text = path.read_text(encoding="utf-8-sig")
        if options["replace_all"]:
            show_limit = max(int(options["show"]), 1)
            outcome = replace_dishes_csv(
                text,
                dry_run=options["dry_run"],
            )
            self._print_errors(outcome["errors"][:show_limit])
            if outcome["errors"]:
                raise CommandError("Replace aborted: fix CSV errors before using --replace-all.")

            prefix = "DRY RUN (no changes committed): " if options["dry_run"] else ""
            self.stdout.write(
                self.style.WARNING(
                    "replace-all mode: the current dishes table will be fully replaced by the CSV contents."
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{prefix}replace-all: deleted={outcome['deleted']} created={outcome['created']} "
                    f"skipped={outcome['skipped']} errors={len(outcome['errors'])}"
                )
            )
            return

        review = review_dishes_csv_import(text)
        show_limit = max(int(options["show"]), 1)

        self.stdout.write(
            "review: "
            f"new={len(review.create_candidates)} "
            f"same={len(review.exact_matches)} "
            f"changed={len(review.changed_matches)} "
            f"similar={len(review.similar_matches)} "
            f"skipped={len(review.skipped)} "
            f"errors={len(review.errors)}"
        )

        self._print_changed(review.changed_matches[:show_limit])
        self._print_similar(review.similar_matches[:show_limit])
        self._print_errors(review.errors[:show_limit])

        outcome = import_dishes_csv_safely(
            text,
            dry_run=options["dry_run"],
            apply_updates=options["apply_updates"],
        )
        prefix = "DRY RUN (no changes committed): " if options["dry_run"] else ""
        mode = "create+update" if options["apply_updates"] else "create-only"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{mode}: created={outcome['created']} updated={outcome['updated']} "
                f"skipped={outcome['skipped']} review_changed={len(outcome['changed_matches'])} "
                f"review_similar={len(outcome['similar_matches'])} errors={len(outcome['errors'])}"
            )
        )

        if review.changed_matches or review.similar_matches:
            self.stdout.write(
                self.style.WARNING(
                    "Review required: changed rows were not overwritten by default, and similar names were not imported automatically."
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    f"Use --apply-updates to accept exact-name field updates after review. Similar-name rows should be merged manually."
                )
            )

    def _print_changed(self, rows):
        for item in rows:
            self.stdout.write(self.style.WARNING(f"changed row {item['row']}: {item['incoming']['ru']}"))
            for field, diff in item.get("changed_fields", {}).items():
                self.stdout.write(f"  {field}: current={diff['current']!r} incoming={diff['incoming']!r}")

    def _print_similar(self, rows):
        for item in rows:
            self.stdout.write(self.style.WARNING(f"similar row {item['row']}: {item['incoming']['ru']}"))
            for suggestion in item.get("suggestions", []):
                score = round(float(suggestion.get("score", 0)) * 100)
                self.stdout.write(f"  -> {suggestion['name']} ({score}%)")

    def _print_errors(self, rows):
        for item in rows:
            self.stdout.write(self.style.ERROR(f"row {item['row']}: {item['error']}"))
