from django.contrib import admin

from .models import IntegrationOperation


@admin.register(IntegrationOperation)
class IntegrationOperationAdmin(admin.ModelAdmin):
    list_display = ("request_id", "kind", "status", "idempotency_key", "created_at", "expires_at")
    search_fields = ("request_id", "idempotency_key")
    list_filter = ("kind", "status")
    readonly_fields = ("created_at", "updated_at")
