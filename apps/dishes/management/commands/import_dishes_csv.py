from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.dishes.services import replace_dishes_csv, review_dishes_csv_import, upsert_dish


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
        progress = self._progress_printer()
        self.stdout.write(f"Reading {path} ({len(text)} bytes)...")

        if options["replace_all"]:
            show_limit = max(int(options["show"]), 1)
            outcome = replace_dishes_csv(
                text,
                dry_run=options["dry_run"],
                progress=progress,
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

        # One review pass with progress, then apply without re-running the expensive review.
        review = review_dishes_csv_import(text, progress=progress)
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

        outcome = self._apply_reviewed(
            review,
            dry_run=options["dry_run"],
            apply_updates=options["apply_updates"],
            progress=progress,
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
                    "Use --apply-updates to accept exact-name field updates after review. Similar-name rows should be merged manually."
                )
            )

    def _apply_reviewed(self, review, dry_run=False, apply_updates=False, progress=None) -> dict:
        outcome = {
            "created": 0,
            "updated": 0,
            "skipped": len(review.skipped) + len(review.exact_matches),
            "changed_matches": review.changed_matches,
            "similar_matches": review.similar_matches,
            "errors": list(review.errors),
        }
        create_total = len(review.create_candidates)
        update_total = len(review.changed_matches) if apply_updates else 0
        apply_total = create_total + update_total
        applied = 0

        with transaction.atomic():
            for item in review.create_candidates:
                try:
                    upsert_dish(item["incoming"], None)
                    outcome["created"] += 1
                except Exception as exc:
                    outcome["errors"].append({"row": item["row"], "error": str(exc)})
                applied += 1
                if progress and apply_total:
                    progress(applied, apply_total, "import")

            if apply_updates:
                for item in review.changed_matches:
                    try:
                        upsert_dish(item["incoming"], None)
                        outcome["updated"] += 1
                    except Exception as exc:
                        outcome["errors"].append({"row": item["row"], "error": str(exc)})
                    applied += 1
                    if progress and apply_total:
                        progress(applied, apply_total, "import")

            if dry_run:
                transaction.set_rollback(True)

        if progress and apply_total:
            progress(apply_total, apply_total, "import")
        return outcome

    def _progress_printer(self):
        last_bucket = {}

        def progress(current, total, phase):
            if total <= 0:
                return
            # About 10 lines max per phase: 0/10/.../100.
            bucket = 10 if current >= total else (10 * current) // total
            if last_bucket.get(phase) == bucket and current < total:
                return
            last_bucket[phase] = bucket
            pct = 100 if current >= total else (100 * current) // total
            self.stdout.write(f"[{phase}] {pct}% ({current}/{total})")
            self.stdout.flush()

        return progress

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
