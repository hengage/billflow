from django.contrib import admin
from .models import IdempotencyKey, Payment, WebhookLog


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'recovery_point', 'locked_at', 'created_at')
    list_filter = ('recovery_point',)
    search_fields = ('user__email', 'key')
    readonly_fields = ('id', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'amount', 'currency', 'status', 'purpose', 'created_at')
    list_filter = ('provider', 'status', 'purpose')
    search_fields = ('user__email', 'reference')
    readonly_fields = ('id', 'idempotency_key', 'created_at', 'updated_at')

    def has_delete_permission(self, request, obj=None):
        # Payment records are an immutable audit trail — never delete
        return False


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ('provider', 'event_type', 'reference', 'processed', 'received_at')
    list_filter = ('provider', 'processed', 'permanently_failed')
    search_fields = ('reference', 'event_type')
    readonly_fields = ('id', 'provider', 'event_type', 'reference', 'payload', 'received_at', 'failure_reason')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
