from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        USER = "user", "User"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    must_change_password = models.BooleanField(default=True)

    @property
    def is_admin(self) -> bool:
        return self.is_authenticated and self.is_active and self.role == self.Role.ADMIN

    @property
    def is_editor(self) -> bool:
        return self.is_authenticated and self.is_active


class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"preferences:{self.user_id}"
