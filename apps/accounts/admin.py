from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, UserPreference


@admin.register(User)
class AppUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Menu AutoPrint", {"fields": ("must_change_password",)}),)
    list_display = ("username", "is_staff", "is_active", "must_change_password")


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")
