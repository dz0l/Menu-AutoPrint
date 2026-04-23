from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path("users", views.users, name="users"),
    path("users/<int:user_id>", views.user_detail, name="user_detail"),
    path("change-password", views.change_password, name="change_password"),
    path("profile", views.profile, name="profile"),
    path("preferences", views.preferences, name="preferences"),
]
