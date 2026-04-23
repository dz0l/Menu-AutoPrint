from django.contrib import admin

from .models import Dish, DishChangeLog


@admin.register(Dish)
class DishAdmin(admin.ModelAdmin):
    list_display = ("name_ru", "name_en", "kcal_per_100", "grams_default", "category_ru", "updated_at")
    search_fields = ("name_ru", "name_en", "category_ru")
    list_filter = ("category_ru",)


@admin.register(DishChangeLog)
class DishChangeLogAdmin(admin.ModelAdmin):
    list_display = ("action", "name_ru_snapshot", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("name_ru_snapshot",)
