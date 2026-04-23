from django.shortcuts import redirect
from django.urls import reverse


class MustChangePasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and getattr(user, "must_change_password", False):
            allowed = {
                reverse("change_password_page"),
                reverse("logout"),
            }
            if request.path not in allowed and not request.path.startswith("/admin/"):
                return redirect("change_password_page")
        return self.get_response(request)
