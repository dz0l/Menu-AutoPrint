"""Shared request helpers for API views."""

from __future__ import annotations

import json

from django.http import HttpRequest


def json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Incorrect JSON.") from exc


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
