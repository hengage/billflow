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
