from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Dish",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name_ru", models.CharField(max_length=255)),
                ("name_ru_norm", models.CharField(editable=False, max_length=255, unique=True)),
                ("name_en", models.CharField(blank=True, max_length=255)),
                ("kcal_per_100", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("grams_default", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("category_ru", models.CharField(blank=True, max_length=120)),
                ("category_en", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_dishes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_dishes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["name_ru"]},
        ),
        migrations.CreateModel(
            name="DishChangeLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dish_id_snapshot", models.BigIntegerField(blank=True, null=True)),
                ("name_ru_snapshot", models.CharField(blank=True, max_length=255)),
                (
                    "action",
                    models.CharField(
                        choices=[("create", "create"), ("update", "update"), ("delete", "delete")],
                        max_length=16,
                    ),
                ),
                ("changed_fields", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dish",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="dishes.dish",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
