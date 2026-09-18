from pathlib import Path

from django.conf import settings
from django.db import migrations, models


def banquet_to_main(apps, schema_editor):
    MenuArchiveEntry = apps.get_model("menu", "MenuArchiveEntry")
    media_root = Path(settings.MEDIA_ROOT)
    for entry in MenuArchiveEntry.objects.filter(menu_type="banquet").iterator():
        conflict = (
            MenuArchiveEntry.objects.filter(
                menu_date=entry.menu_date,
                menu_type="main",
                location_key=entry.location_key,
            )
            .exclude(pk=entry.pk)
            .first()
        )
        if conflict:
            # Prefer existing main; drop banquet row and orphan file if distinct.
            banquet_path = media_root / (entry.relative_path or "")
            main_path = media_root / (conflict.relative_path or "")
            if banquet_path.is_file() and banquet_path.resolve() != main_path.resolve():
                try:
                    banquet_path.unlink()
                except OSError:
                    pass
            entry.delete()
            continue
        entry.menu_type = "main"
        # Keep display_name; strip legacy banquet suffix if present.
        name = (entry.display_name or "").replace(" (банкет)", "")
        if name != entry.display_name:
            entry.display_name = name
        entry.save(update_fields=["menu_type", "display_name", "updated_at"])


def noop_reverse(apps, schema_editor):
    # Irreversible data merge.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0004_menucover"),
    ]

    operations = [
        migrations.RunPython(banquet_to_main, noop_reverse),
        migrations.AlterField(
            model_name="menuarchiveentry",
            name="menu_type",
            field=models.CharField(
                choices=[("breakfast", "Breakfast"), ("main", "Main")],
                db_index=True,
                max_length=16,
            ),
        ),
    ]
