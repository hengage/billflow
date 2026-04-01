from django.db import models
from django.conf import settings
import uuid
from .constants import (
    IdempotencyRecoveryPoint,
    PaymentProvider, 
    PaymentPurpose, 
    PaymentStatus, 
    Currency,
)


class IdempotencyKey(models.Model):
    """
    Implements the 'Idempotent Consumer' pattern to ensure that retried 
    HTTP requests do not result in duplicate side effects.
    
    This model follows the implementation logic outlined by Brandur Leach 
    in "Idempotency Keys" (https://brandur.org/idempotency-keys).
    
    It acts as a distributed lock and state machine. The 'request_path' 
    is included in the uniqueness constraint to namespace keys, ensuring 
    that a single UUID is not accidentally reused across different API 
    endpoints (e.g., preventing a wallet top-up key from being used for 
    a subscription purchase).
    
    Attributes:
        user (FK): The authenticated user making the request.
        key (str): The unique string from the X-Idempotency-Key header.
        request_path (str): The API path (e.g., /api/wallets/top-up/) 
            used to namespace the key.
        recovery_point (str): The current state of the request in the 
            orchestrator loop.
        locked_at (datetime): Used to prevent race conditions (double-taps).
        request_params (json): A snapshot of the original request body.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    request_path = models.CharField(max_length=255)
    
    recovery_point = models.CharField(
        max_length=50, 
        choices=IdempotencyRecoveryPoint.choices,
        default=IdempotencyRecoveryPoint.STARTED
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    
    request_params = models.JSONField()
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Uniqueness scoped to User + Key + Path
        unique_together = ('user', 'key', 'request_path')
        
        # High-performance composite index for rapid lookups
        indexes = [
            models.Index(fields=['user', 'key', 'request_path']),
        ]


class Payment(models.Model):
    """
    The source of truth for a financial intent.
    The 'id' (UUID) is sent to Paystack/Stripe as the unique 'reference'.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="payments"
    )
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency, default=Currency.NGN)

    provider = models.CharField(
        max_length=20,
        choices=PaymentProvider
    )
    purpose = models.CharField(
        max_length=50,
        choices=PaymentPurpose
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus,
        default=PaymentStatus.PENDING
    )
    
    # Link to the key that initiated this
    idempotency_key = models.OneToOneField(
        'IdempotencyKey', 
        on_delete=models.SET_NULL, 
        null=True,
        related_name="payment"
    )
    
    # Provider transaction details
    reference = models.CharField(max_length=255, blank=True)  # provider's transaction ID
    last_four = models.CharField(max_length=4, blank=True)    # PCI DSS — store only this
    card_brand = models.CharField(max_length=20, blank=True)  # visa, mastercard etc.
    
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount} - {self.purpose} - {self.status}"


class WebhookLog(models.Model):
    """
    Immutable audit trail of every incoming webhook event.

    Written BEFORE any processing — if processing fails, the raw payload
    is here to inspect, debug, and replay. The processed flag tells us
    which events were handled successfully and which need attention.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20, choices=PaymentProvider.choices)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f'{self.provider} | {self.event_type} | processed={self.processed}'
