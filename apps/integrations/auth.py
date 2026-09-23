from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


CONTRACT_VERSION = "1"


def hash_api_key(raw_key: str) -> str:
    pepper = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(pepper, raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def integration_error(status: int, code: str, message: str, *, details=None, request_id: str | None = None):
    body = {"error": {"code": code, "message": message, "details": details or []}}
    if request_id:
        body["request_id"] = request_id
    return JsonResponse(body, status=status)


def resolve_service_user():
    User = get_user_model()
    user_id = settings.INTEGRATION_SERVICE_USER_ID
    if not user_id:
        return None
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None
    if not user.is_active or not getattr(user, "is_admin", False):
        return None
    return user


def authenticate_integration(request):
    if not settings.INTEGRATION_API_ENABLED:
        return None, integration_error(403, "integration_disabled", "Integration API is disabled.")
    expected = (settings.INTEGRATION_API_KEY_HASH or "").strip()
    if not expected:
        return None, integration_error(403, "integration_disabled", "Integration API is disabled.")
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    if not header.lower().startswith("bearer "):
        return None, integration_error(401, "unauthorized", "Bearer credential required.")
    token = header.split(" ", 1)[1].strip()
    if not token or not hmac.compare_digest(hash_api_key(token), expected):
        return None, integration_error(401, "unauthorized", "Invalid credential.")
    user = resolve_service_user()
    if user is None:
        return None, integration_error(403, "integration_disabled", "Service user is unavailable.")
    return user, None


def integration_endpoint(view):
    @csrf_exempt
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user, error = authenticate_integration(request)
        if error is not None:
            return error
        request.integration_user = user
        # Avoid MustChangePasswordMiddleware redirect: mark path as API already skipped there.
        return view(request, *args, **kwargs)

    return wrapper
