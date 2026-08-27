from django.conf import settings
from django.db import models


class MenuArchiveEntry(models.Model):
    class MenuType(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        MAIN = "main", "Main"
        BANQUET = "banquet", "Banquet"

    menu_date = models.DateField(db_index=True)
    menu_type = models.CharField(max_length=16, choices=MenuType.choices, db_index=True)
    location_key = models.CharField(max_length=64, db_index=True, default="unknown_location")
    display_name = models.CharField(max_length=255, blank=True, default="")
    relative_path = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="menu_archive_entries",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["menu_date", "menu_type", "location_key"],
                name="uniq_menu_archive_date_type_location",
            ),
        ]
        ordering = ["-menu_date", "location_key", "menu_type"]

    def __str__(self) -> str:
        return f"{self.menu_date.isoformat()}_{self.menu_type}_{self.location_key}"


class MenuCover(models.Model):
    """Server-stored PDF background image with a display location name."""

    location_name = models.CharField(max_length=128)
    original_filename = models.CharField(max_length=255)
    relative_path = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="menu_covers",
    )

    class Meta:
        ordering = ["location_name", "id"]

    def __str__(self) -> str:
        return self.location_name

    @property
    def location_key(self) -> str:
        return f"c{self.id}"
