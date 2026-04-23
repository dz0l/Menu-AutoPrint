import json

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .models import UserPreference


User = get_user_model()


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _editor_required(request):
    return request.user.is_authenticated and request.user.is_active


@require_http_methods(["GET", "POST"])
def users(request):
    if not _editor_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    if request.method == "GET":
        return JsonResponse(
            {
                "users": [
                    {"id": u.id, "username": u.username, "is_madmin": u.username == "mAdmin"}
                    for u in User.objects.order_by("username")
                ]
            }
        )

    data = _json_body(request)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return JsonResponse({"error": "username and password required"}, status=400)
    try:
        validate_password(password)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)
    user = User.objects.create_user(username=username, password=password, must_change_password=True)
    return JsonResponse({"id": user.id, "username": user.username}, status=201)


@require_http_methods(["DELETE"])
def user_detail(request, user_id):
    if not _editor_required(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    user = User.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({"error": "not found"}, status=404)
    if user.username == "mAdmin":
        return JsonResponse({"error": "mAdmin cannot be deleted"}, status=400)
    user.delete()
    return JsonResponse({"deleted": True})


@login_required
def change_password_page(request):
    if request.method == "GET":
        return render(request, "registration/change_password.html")

    old_password = request.POST.get("old_password") or ""
    new_password = request.POST.get("new_password") or ""
    if not request.user.check_password(old_password):
        return render(request, "registration/change_password.html", {"error": "Текущий пароль указан неверно."}, status=400)
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
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""
    if not request.user.check_password(old_password):
        return JsonResponse({"error": "invalid current password"}, status=400)
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
