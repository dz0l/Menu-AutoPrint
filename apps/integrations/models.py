from django.db import models


class IntegrationOperation(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_SUCCEEDED, "succeeded"),
        (STATUS_FAILED, "failed"),
    ]

    KIND_CREATE_DISH = "create_dish"
    KIND_PDF = "pdf"
    KIND_CHOICES = [
        (KIND_CREATE_DISH, "create_dish"),
        (KIND_PDF, "pdf"),
    ]

    request_id = models.CharField(max_length=64, unique=True, db_index=True)
    scope = models.CharField(max_length=64, default="default")
    idempotency_key = models.CharField(max_length=128)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    result_json = models.JSONField(default=dict, blank=True)
    result_path = models.CharField(max_length=512, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "kind", "idempotency_key"],
                name="uniq_integration_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.idempotency_key}:{self.status}"
