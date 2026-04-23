from django.conf import settings
from django.db import models

from apps.core.text import normalize_ru


class Dish(models.Model):
    name_ru = models.CharField(max_length=255)
    name_ru_norm = models.CharField(max_length=255, unique=True, editable=False)
    name_en = models.CharField(max_length=255, blank=True)
    kcal_per_100 = models.PositiveSmallIntegerField(null=True, blank=True)
    grams_default = models.PositiveSmallIntegerField(null=True, blank=True)
    category_ru = models.CharField(max_length=120, blank=True)
    category_en = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_dishes")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_dishes")

    class Meta:
        ordering = ["name_ru"]

    def save(self, *args, **kwargs):
        self.name_ru = (self.name_ru or "").strip()
        self.name_ru_norm = normalize_ru(self.name_ru)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name_ru


class DishChangeLog(models.Model):
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_CHOICES = [
        (ACTION_CREATE, "create"),
        (ACTION_UPDATE, "update"),
        (ACTION_DELETE, "delete"),
    ]

    dish = models.ForeignKey(Dish, null=True, blank=True, on_delete=models.SET_NULL)
    dish_id_snapshot = models.BigIntegerField(null=True, blank=True)
    name_ru_snapshot = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    changed_fields = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
