from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    SUCCESS = 'success', _('Success')
    FAILED = 'failed', _('Failed')
    CANCELLED = 'cancelled', _('Cancelled')


class PaymentPurpose(models.TextChoices):
    WALLET_TOPUP = 'wallet_topup', _('Wallet Top-up')
    SUBSCRIPTION = 'subscription', _('Subscription Payment')


class PaymentProvider(models.TextChoices):
    PAYSTACK = 'paystack', _('Paystack')
    STRIPE = 'stripe', _('Stripe')


class IdempotencyRecoveryPoint(models.TextChoices):
    STARTED = 'started', _('Started')
    PAYMENT_CREATED = 'payment_created', _('Payment Created')
    PROVIDER_INITIALIZED = 'provider_initialized', _('Provider Initialized')
    FINISHED = 'finished', _('Finished')


class Currency(models.TextChoices):
    NGN = 'NGN', _('Nigerian Naira')
    USD = 'USD', _('US Dollar')


class PaystackEvent:
    """
    Paystack webhook event type constants.
    Reference: https://paystack.com/docs/payments/webhooks/#supported-events
    """
    CHARGE_SUCCESS = 'charge.success'


class StripeEvent:
    """
    Stripe webhook event type constants.
    Reference: https://stripe.com/docs/api/events/types
    """
    PAYMENT_INTENT_SUCCEEDED = 'payment_intent.succeeded'
    PAYMENT_INTENT_FAILED = 'payment_intent.payment_failed'


# HTTP status codes that Paystack returns for permanent rejections.
# These indicate a non-retryable failure — the provider rejected the
# request for a business reason that won't change on retry.
PAYSTACK_NON_RETRYABLE_STATUS_CODES = {400, 422}
