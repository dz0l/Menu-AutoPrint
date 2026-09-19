"""Shared request helpers for API views."""

from __future__ import annotations

import json
import re

from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.http import HttpRequest

_USERNAME_VALIDATOR = UnicodeUsernameValidator()


def json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON.") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Waiting for JSON object.")
    return data


def request_payload(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        return json_body(request)
    return request.POST.dict()


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "off", "none"}


def editor_required(request: HttpRequest) -> bool:
    return bool(request.user.is_authenticated and request.user.is_active)


def admin_required(request: HttpRequest) -> bool:
    return editor_required(request) and bool(getattr(request.user, "is_admin", False))


def validate_username_value(username: str) -> str:
    value = (username or "").strip()
    if not value:
        raise ValueError("username required")
    if len(value) > 150:
        raise ValueError("username too long")
    if re.search(r"[<>\"'`]", value):
        raise ValueError("username contains invalid characters")
    try:
        _USERNAME_VALIDATOR(value)
    except ValidationError as exc:
        raise ValueError("; ".join(exc.messages)) from exc
    return value
