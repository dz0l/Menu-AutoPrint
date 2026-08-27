import re
from pathlib import Path

from django.db import migrations, models

# Historical data migration helper (do not import app modules here).
_COVER_LOCATIONS = {
    "3k.jpg": "3й корпус",
    "airlines.jpg": "Самолёт",
    "banket.jpg": "Банкет",
    "board.jpg": "Лодка",
    "dd.jpg": "ДД",
    "dubai.jpg": "Дубай",
    "kd.jpg": "КД",
    "kd-ng.jpg": "КД НГ",
    "mandarin.jpg": "Mandarin",
    "max.jpg": "MaxxRoyal",
    "spa.jpg": "СПА",
    "tash.jpg": "Ташкент",
    "train.jpg": "Поезд",
    "vil126.jpg": "Вилла-126",
}

UNKNOWN_LOCATION_KEY = "unknown_location"
_LOCATION_LABEL_TO_KEY = {label: Path(filename).stem for filename, label in _COVER_LOCATIONS.items()}


def _location_key_from_display_name(display_name: str) -> str:
    raw = (display_name or "").strip()
    if not raw:
        return UNKNOWN_LOCATION_KEY
    cleaned = raw.replace(" (завтрак)", "").replace(" (банкет)", "").strip()
    if " - " in cleaned:
        label = cleaned.split(" - ", 1)[1].strip()
    else:
        label = cleaned
    if not label or label == UNKNOWN_LOCATION_KEY:
        return UNKNOWN_LOCATION_KEY
    if label in _LOCATION_LABEL_TO_KEY:
        return _LOCATION_LABEL_TO_KEY[label]
    safe = re.sub(r"[^a-z0-9._-]+", "_", label.lower()).strip("._-")
    return safe or UNKNOWN_LOCATION_KEY


def forwards_fill_location_key(apps, schema_editor):
    from django.conf import settings

    MenuArchiveEntry = apps.get_model("menu", "MenuArchiveEntry")
    media_root = Path(settings.MEDIA_ROOT)
    for entry in MenuArchiveEntry.objects.all().iterator():
        key = _location_key_from_display_name(getattr(entry, "display_name", "") or "")
        new_relative = f"menu_archive/{entry.menu_date.isoformat()}_{entry.menu_type}_{key}.pdf"
        old_relative = (entry.relative_path or "").replace("\\", "/")
        update_fields = []
        if entry.location_key != key:
            entry.location_key = key
            update_fields.append("location_key")
        if old_relative != new_relative:
            old_path = media_root / old_relative if old_relative else None
            new_path = media_root / new_relative
            new_path.parent.mkdir(parents=True, exist_ok=True)
            if old_path and old_path.is_file() and old_path.resolve() != new_path.resolve():
                if new_path.exists():
                    new_path.unlink()
                old_path.replace(new_path)
            entry.relative_path = new_relative
            update_fields.append("relative_path")
        if update_fields:
            entry.save(update_fields=update_fields)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0002_menuarchiveentry_display_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="menuarchiveentry",
            name="location_key",
            field=models.CharField(db_index=True, default="unknown_location", max_length=64),
        ),
        migrations.RunPython(forwards_fill_location_key, backwards_noop),
        migrations.RemoveConstraint(
            model_name="menuarchiveentry",
            name="uniq_menu_archive_date_type",
        ),
        migrations.AlterModelOptions(
            name="menuarchiveentry",
            options={"ordering": ["-menu_date", "location_key", "menu_type"]},
        ),
        migrations.AddConstraint(
            model_name="menuarchiveentry",
            constraint=models.UniqueConstraint(
                fields=("menu_date", "menu_type", "location_key"),
                name="uniq_menu_archive_date_type_location",
            ),
        ),
    ]
