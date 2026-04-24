import json

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods

from .models import UserPreference


User = get_user_model()


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _editor_required(request):
    return request.user.is_authenticated and request.user.is_active


def _madmin_required(request):
    return _editor_required(request) and request.user.username == "mAdmin"


def _serialize_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "is_madmin": user.username == "mAdmin",
        "must_change_password": user.must_change_password,
    }


def _generate_valid_password(user=None) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*"
    for _ in range(10):
        password = get_random_string(14, allowed_chars=alphabet)
        try:
            validate_password(password, user)
        except ValidationError:
            continue
        return password
    return get_random_string(18, allowed_chars=alphabet)


@require_http_methods(["GET", "POST"])
def users(request):
    if not _madmin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)

    if request.method == "GET":
        return JsonResponse({"users": [_serialize_user(u) for u in User.objects.order_by("username")]})

    data = _json_body(request)
    username = (data.get("username") or "").strip()
    password = data.get("password") or _generate_valid_password()
    if not username:
        return JsonResponse({"error": "username required"}, status=400)

    try:
        validate_password(password)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)

    try:
        user = User.objects.create_user(username=username, password=password, must_change_password=True)
    except IntegrityError:
        return JsonResponse({"error": "username already exists"}, status=400)

    return JsonResponse({"user": _serialize_user(user), "generated_password": password}, status=201)


@require_http_methods(["DELETE"])
def user_detail(request, user_id):
    if not _madmin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)

    user = User.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({"error": "not found"}, status=404)
    if user.username == "mAdmin":
        return JsonResponse({"error": "mAdmin cannot be deleted"}, status=400)

    user.delete()
    return JsonResponse({"deleted": True})


@require_http_methods(["POST"])
def user_reset_password(request, user_id):
    if not _madmin_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)

    user = User.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({"error": "not found"}, status=404)
    if user.username == "mAdmin":
        return JsonResponse({"error": "mAdmin password cannot be reset here"}, status=400)

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
        validate_password(new_password, request.user)
    except ValidationError as exc:
        return render(request, "registration/change_password.html", {"errors": exc.messages}, status=400)

    request.user.set_password(new_password)
    request.user.must_change_password = False
    request.user.save(update_fields=["password", "must_change_password"])
    update_session_auth_hash(request, request.user)
    return redirect("menu:index")


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    if request.method == "GET":
        return JsonResponse({"must_change_password": request.user.must_change_password})

    data = _json_body(request)
    new_password = data.get("new_password") or ""
    new_password_repeat = data.get("new_password_repeat") or ""
    if new_password != new_password_repeat:
        return JsonResponse({"error": "passwords do not match"}, status=400)

    try:
        validate_password(new_password, request.user)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)

    request.user.set_password(new_password)
    request.user.must_change_password = False
    request.user.save(update_fields=["password", "must_change_password"])
    update_session_auth_hash(request, request.user)
    return JsonResponse({"changed": True})


@login_required
@require_http_methods(["GET", "PATCH"])
def profile(request):
    if request.method == "GET":
        return JsonResponse({"username": request.user.username})
    data = _json_body(request)
    username = (data.get("username") or "").strip()
    if not username:
        return JsonResponse({"error": "username required"}, status=400)
    request.user.username = username
    request.user.save(update_fields=["username"])
    return JsonResponse({"username": request.user.username})


@require_http_methods(["GET", "PATCH"])
def preferences(request):
    if request.user.is_authenticated:
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
        if request.method == "GET":
            return JsonResponse({"preferences": pref.data})
        pref.data.update(_json_body(request))
        pref.save(update_fields=["data", "updated_at"])
        return JsonResponse({"preferences": pref.data})

    if request.method == "GET":
        return JsonResponse({"preferences": request.session.get("ui_preferences", {})})
    prefs = request.session.get("ui_preferences", {})
    prefs.update(_json_body(request))
    request.session["ui_preferences"] = prefs
    return JsonResponse({"preferences": prefs})
