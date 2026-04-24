from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.views import RateLimitedLoginView, change_password_page
from apps.core.views import healthcheck


urlpatterns = [
    path("", include("apps.menu.urls")),
    path("favicon.ico", RedirectView.as_view(url="/static/favicon.ico", permanent=True)),
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
    path("accounts/login/", RateLimitedLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/change-password/", change_password_page, name="change_password_page"),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/dishes/", include("apps.dishes.urls")),
    path("api/menu/", include("apps.menu.api_urls")),
]
