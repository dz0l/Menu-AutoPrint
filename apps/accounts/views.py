import json
import re

from django.conf import settings
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods

from apps.core.http_utils import admin_required as _admin_required
from apps.core.http_utils import json_body as _json_body
from apps.core.http_utils import validate_username_value
from .models import UserPreference


User = get_user_model()


class RateLimitedLoginView(LoginView):
    template_name = "registration/login.html"

    def post(self, request, *args, **kwargs):
        username_field = getattr(User, "USERNAME_FIELD", "username")
        username = (request.POST.get(username_field) or "").strip().lower()
        # Prefer REMOTE_ADDR; do not trust first XFF hop without a trusted proxy policy.
        ident = request.META.get("REMOTE_ADDR", "unknown")
        key = f"login-rate:{ident}:{username}"
        window = settings.LOGIN_RATE_LIMIT_WINDOW
        if cache.add(key, 1, window):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, window)
                count = 1
        if count > settings.LOGIN_RATE_LIMIT_COUNT:
            form = self.get_form()
            form.add_error(None, "Слишком много попыток входа. Попробуйте позже.")
            return self.form_invalid(form)

        response = super().post(request, *args, **kwargs)
        if response.status_code == 302:
            cache.delete(key)
        return response


def _serialize_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": user.is_admin,
        "must_change_password": user.must_change_password,
    }


def _generate_valid_password(user=None) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*"
    for _ in range(40):
        password = get_random_string(14, allowed_chars=alphabet)
        # Ensure mixed character classes for validators that require them.
        if not re.search(r"[A-Z]", password):
            continue
        if not re.search(r"[a-z]", password):
            continue
        if not re.search(r"[0-9]", password):
            continue
        if not re.search(r"[!@#$%^&*]", password):
            continue
        try:
            validate_password(password, user)
        except ValidationError:
            continue
        return password
    # Last resort: still validate; never return an unvalidated string.
    for _ in range(20):
        password = get_random_string(18, allowed_chars=alphabet)
        try:
            validate_password(password, user)
            return password
        except ValidationError:
            continue
    raise RuntimeError("Unable to generate a valid password")


@require_http_methods(["GET", "POST"])
def users(request):
    if not _admin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)

    if request.method == "GET":
        return JsonResponse({"users": [_serialize_user(u) for u in User.objects.order_by("username")]})

    try:
        data = _json_body(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    try:
        username = validate_username_value(data.get("username") or "")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    password = data.get("password") or _generate_valid_password()

    try:
        validate_password(password)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)

    try:
        user = User.objects.create_user(
            username=username,
            password=password,
            role=User.Role.USER,
            must_change_password=True,
        )
    except IntegrityError:
        return JsonResponse({"error": "username already exists"}, status=400)

    return JsonResponse({"user": _serialize_user(user), "generated_password": password}, status=201)


@require_http_methods(["DELETE"])
def user_detail(request, user_id):
    if not _admin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)

    user = User.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({"error": "not found"}, status=404)
    if user.is_admin:
        return JsonResponse({"error": "admin users cannot be deleted here"}, status=400)

    user.delete()
    return JsonResponse({"deleted": True})


@require_http_methods(["POST"])
def user_reset_password(request, user_id):
    if not _admin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)

    user = User.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({"error": "not found"}, status=404)
    if user.is_admin:
        return JsonResponse({"error": "admin user passwords cannot be reset here"}, status=400)

    password = _generate_valid_password(user)
    user.set_password(password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    return JsonResponse({"reset": True, "generated_password": password, "user": _serialize_user(user)})


@login_required
def change_password_page(request):
    if request.method == "GET":
        return render(request, "registration/change_password.html")

    new_password = request.POST.get("new_password") or ""
    new_password_repeat = request.POST.get("new_password_repeat") or ""
    if new_password != new_password_repeat:
        return render(
            request,
            "registration/change_password.html",
            {"error": "Новые пароли не совпадают."},
            status=400,
        )

    try:
        _apply_password_change(request, new_password)
    except ValidationError as exc:
        return render(request, "registration/change_password.html", {"errors": exc.messages}, status=400)
    return redirect("menu:index")


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    if request.method == "GET":
        return JsonResponse({"must_change_password": request.user.must_change_password})

    try:
        data = _json_body(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    new_password = data.get("new_password") or ""
    new_password_repeat = data.get("new_password_repeat") or ""
    if new_password != new_password_repeat:
        return JsonResponse({"error": "passwords do not match"}, status=400)

    try:
        _apply_password_change(request, new_password)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)
    return JsonResponse({"changed": True})


def _apply_password_change(request, new_password: str) -> None:
    validate_password(new_password, request.user)
    request.user.set_password(new_password)
    request.user.must_change_password = False
    request.user.save(update_fields=["password", "must_change_password"])
    update_session_auth_hash(request, request.user)


@login_required
@require_http_methods(["GET", "PATCH"])
def profile(request):
    if request.method == "GET":
        return JsonResponse({"username": request.user.username})
    try:
        data = _json_body(request)
        username = validate_username_value(data.get("username") or "")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    request.user.username = username
    try:
        request.user.save(update_fields=["username"])
    except IntegrityError:
        return JsonResponse({"error": "username already exists"}, status=400)
    return JsonResponse({"username": request.user.username})


@require_http_methods(["GET", "PATCH"])
def preferences(request):
    if request.user.is_authenticated:
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
        if request.method == "GET":
            return JsonResponse({"preferences": pref.data})
        try:
            pref.data.update(_json_body(request))
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        pref.save(update_fields=["data", "updated_at"])
        return JsonResponse({"preferences": pref.data})

    if request.method == "GET":
        return JsonResponse({"preferences": request.session.get("ui_preferences", {})})
    try:
        prefs = request.session.get("ui_preferences", {})
        prefs.update(_json_body(request))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    request.session["ui_preferences"] = prefs
    return JsonResponse({"preferences": prefs})
