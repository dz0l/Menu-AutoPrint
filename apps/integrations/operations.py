from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import IntegrationOperation

# Stuck pending older than this may be reclaimed on a retry with the same key (W-05 minimum).
PENDING_STALE_SECONDS = 180


def payload_hash(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def operations_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / "integration_operations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def purge_expired_operations() -> None:
    now = timezone.now()
    expired = list(IntegrationOperation.objects.filter(expires_at__lte=now)[:200])
    for op in expired:
        if op.result_path:
            path = Path(settings.MEDIA_ROOT) / op.result_path
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        op.delete()


def begin_operation(*, scope: str, kind: str, idempotency_key: str, payload) -> tuple[IntegrationOperation, bool]:
    """Return (operation, is_replay). Raises IntegrationOperationConflict."""
    purge_expired_operations()
    digest = payload_hash(payload)
    ttl_hours = max(1, int(settings.INTEGRATION_OPERATION_TTL_HOURS))
    expires_at = timezone.now() + timedelta(hours=ttl_hours)
    request_id = secrets.token_hex(16)
    create_kwargs = {
        "request_id": request_id,
        "scope": scope,
        "idempotency_key": idempotency_key,
        "kind": kind,
        "payload_hash": digest,
        "status": IntegrationOperation.STATUS_PENDING,
        "expires_at": expires_at,
    }
    try:
        with transaction.atomic():
            op = IntegrationOperation.objects.create(**create_kwargs)
        return op, False
    except IntegrityError:
        existing = IntegrationOperation.objects.get(scope=scope, kind=kind, idempotency_key=idempotency_key)
        if existing.payload_hash != digest:
            raise IntegrationOperationConflict("idempotency_conflict", "Idempotency key reused with different payload.")
        if existing.status == IntegrationOperation.STATUS_PENDING:
            age = (timezone.now() - existing.updated_at).total_seconds()
            if age >= PENDING_STALE_SECONDS:
                reclaim_id = secrets.token_hex(16)
                with transaction.atomic():
                    deleted, _ = IntegrationOperation.objects.filter(
                        pk=existing.pk,
                        status=IntegrationOperation.STATUS_PENDING,
                    ).delete()
                    if deleted:
                        create_kwargs["request_id"] = reclaim_id
                        create_kwargs["expires_at"] = timezone.now() + timedelta(hours=ttl_hours)
                        try:
                            op = IntegrationOperation.objects.create(**create_kwargs)
                            return op, False
                        except IntegrityError:
                            pass
                existing = IntegrationOperation.objects.get(scope=scope, kind=kind, idempotency_key=idempotency_key)
        return existing, True


class IntegrationOperationConflict(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def mark_succeeded(op: IntegrationOperation, *, result_json: dict | None = None, pdf: bytes | None = None, filename: str = "") -> IntegrationOperation:
    updates = {
        "status": IntegrationOperation.STATUS_SUCCEEDED,
        "http_status": 200,
        "error_code": "",
        "error_message": "",
        "result_json": result_json or {},
    }
    if pdf is not None:
        relative = f"integration_operations/{op.request_id}.pdf"
        path = Path(settings.MEDIA_ROOT) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf)
        updates["result_path"] = relative
        meta = dict(updates["result_json"])
        meta["filename"] = filename or meta.get("filename") or "menu.pdf"
        meta["size"] = len(pdf)
        updates["result_json"] = meta
    for key, value in updates.items():
        setattr(op, key, value)
    op.save(update_fields=[*updates.keys(), "updated_at"])
    return op


def mark_failed(op: IntegrationOperation, *, http_status: int, code: str, message: str) -> IntegrationOperation:
    op.status = IntegrationOperation.STATUS_FAILED
    op.http_status = http_status
    op.error_code = code
    op.error_message = message
    op.save(update_fields=["status", "http_status", "error_code", "error_message", "updated_at"])
    return op


def read_operation_pdf(op: IntegrationOperation) -> bytes | None:
    if not op.result_path:
        return None
    path = Path(settings.MEDIA_ROOT) / op.result_path
    if not path.is_file():
        return None
    return path.read_bytes()
