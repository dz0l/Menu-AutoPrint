# Generated manually for MenuArchiveEntry

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MenuArchiveEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("menu_date", models.DateField(db_index=True)),
                (
                    "menu_type",
                    models.CharField(
                        choices=[("breakfast", "Breakfast"), ("main", "Main"), ("banquet", "Banquet")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("relative_path", models.CharField(max_length=255)),
                ("file_size", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="menu_archive_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-menu_date", "menu_type"],
            },
        ),
        migrations.AddConstraint(
            model_name="menuarchiveentry",
            constraint=models.UniqueConstraint(fields=("menu_date", "menu_type"), name="uniq_menu_archive_date_type"),
        ),
    ]
