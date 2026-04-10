# apps/subscriptions/models.py
import uuid
from django.conf import settings
from django.db import models


class Plan(models.Model):
    """
    The product billflow sells.
    """
    class BillingCycle(models.TextChoices):
        MONTHLY = 'monthly', 'Monthly'
        YEARLY = 'yearly', 'Yearly'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    monthly_price_ngn = models.DecimalField(max_digits=12, decimal_places=2)
    yearly_price_ngn = models.DecimalField(max_digits=12, decimal_places=2)
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['monthly_price_ngn']

    def __str__(self):
        return f'{self.name} — NGN {self.monthly_price_ngn}/month | NGN {self.yearly_price_ngn}/year'


class Subscription(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
        RENEWED = 'renewed', 'Renewed'

    class BillingCycle(models.TextChoices):
        MONTHLY = 'monthly', 'Monthly'
        YEARLY = 'yearly', 'Yearly'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    billing_cycle = models.CharField(
        max_length=20,
        choices=BillingCycle.choices,
    )
    # Snapshot of the price at subscription time — if plan prices change later,
    # existing subscriptions keep the price they were activated at
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    start_date_utc = models.DateTimeField()
    end_date_utc = models.DateTimeField()
    payment = models.OneToOneField(
        'payments.Payment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscription',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Auto-renewal tracking
    renewal_attempts = models.PositiveSmallIntegerField(default=0)
    last_renewal_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'end_date_utc']),
        ]

    def __str__(self):
        return f'{self.user.email} — {self.plan.name} — {self.billing_cycle} — {self.status}'