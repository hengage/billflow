from django.db import models

class NotificationType(models.TextChoices):
    PAYMENT_SUCCESS = 'payment_success', 'Payment Success'
    PAYMENT_FAILED = 'payment_failed', 'Payment Failed'
    WALLET_TOPUP = 'wallet_topup', 'Wallet Top Up'
    SUBSCRIPTION_EXPIRING = 'subscription_expiring', 'Subscription Expiring'
    SUBSCRIPTION_EXPIRED = 'subscription_expired', 'Subscription Expired'
    SUBSCRIPTION_ACTIVATED = 'subscription_activated', 'Subscription Activated'
    INSUFFICIENT_BALANCE = 'insufficient_balance', 'Insufficient Balance'

class NotificationChannel(models.TextChoices):
    EMAIL = 'email', 'Email'
    PUSH = 'push', 'Push'
