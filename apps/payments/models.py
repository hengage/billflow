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
    
    # Failure reason when payment is declined/failed
    failure_reason = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount} - {self.purpose} - {self.status}"


class WebhookLog(models.Model):
    """
    Immutable audit trail of every incoming webhook event.

    Written BEFORE any processing — if processing fails, the raw payload
    is here to inspect, debug, and replay. The processed flag tells
    which events were handled successfully and which need attention.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20, choices=PaymentProvider.choices)
    event_type = models.CharField(max_length=100)
    reference = models.CharField(max_length=255, blank=True)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    permanently_failed = models.BooleanField(default=False)  # Marked True by the task's on_failure hook when max_retries is exhausted.
    failure_reason = models.TextField(blank=True)  # Stores the final exception message.

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['reference', 'received_at']),
        ]

    def save(self, *args, **kwargs):
        # Auto-extract reference from payload before saving
        if not self.reference and self.payload:
            data = self.payload.get('data', {})
            self.reference = data.get('reference', '')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.provider} | {self.event_type} | ref={self.reference or "N/A"} | processed={self.processed}'


class StoredPaymentMethod(models.Model):
    """
    Stores tokenized payment method references for recurring charges.

    PCI DSS compliance: raw card data is never stored.
    authorization_code (Paystack) and payment_method_id (Stripe) are tokens
    that represent the card on the provider's servers — not the card itself.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='stored_payment_methods',
    )
    provider = models.CharField(max_length=20, choices=PaymentProvider.choices)

    # --- Provider-agnostic token fields ---
    # authorization_code (Paystack) or payment_method_id (Stripe)
    # The provider's token for charging this card
    authorization_code = models.CharField(max_length=100, blank=True)

    # provider_customer_id: customer_code (Paystack) or customer_id cus_xxx (Stripe)
    # Required for off-session/recurring charges
    provider_customer_id = models.CharField(max_length=100, blank=True)

    # The email tied to this authorization at creation time
    # May differ from user's current email — critical for Paystack
    billing_email = models.CharField(max_length=255, blank=True)
    
    # signature: Paystack's signature or Stripe's fingerprint
    # Deduplication key — unique per card per provider
    signature = models.CharField(max_length=100, blank=True)

    # --- Display fields ---
    last_four = models.CharField(max_length=4)
    card_brand = models.CharField(max_length=20)
    exp_month = models.CharField(max_length=2)
    exp_year = models.CharField(max_length=4)
    bank = models.CharField(max_length=100, blank=True)
    card_type = models.CharField(max_length=50, blank=True)  # debit, credit

    # Only reusable authorizations can be charged recurrently.
    # Paystack's reusable field from the authorization object.
    is_reusable = models.BooleanField(default=True)

    # The user's default payment method for auto-renewal
    is_default = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Prevent storing the same card twice for the same user
        # signature is Paystack's unique identifier per card
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'signature'],
                condition=models.Q(provider='paystack'),
                name='unique_paystack_card_per_user',
            ),
            models.UniqueConstraint(
                fields=['user', 'authorization_code'],
                condition=models.Q(provider='stripe'),
                name='unique_stripe_method_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.user.email} — {self.card_brand} ****{self.last_four} ({self.provider})'
