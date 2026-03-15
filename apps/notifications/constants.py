from django.db import models


class NotificationType(models.TextChoices):
    PAYMENT_SUCCESS = 'payment_success', 'Payment Success'
    PAYMENT_FAILED = 'payment_failed', 'Payment Failed'
    WALLET_TOPUP = 'wallet_topup', 'Wallet Top Up'
    SUBSCRIPTION_EXPIRING = 'subscription_expiring', 'Subscription Expiring'
    SUBSCRIPTION_EXPIRED = 'subscription_expired', 'Subscription Expired'
    SUBSCRIPTION_ACTIVATED = 'subscription_activated', 'Subscription Activated'


class NotificationChannel(models.TextChoices):
    EMAIL = 'email', 'Email'
    PUSH = 'push', 'Push'


class NotificationGroup:
    PAYMENTS = 'payments'
    SUBSCRIPTIONS = 'subscriptions'
    WALLET = 'wallet'


# Maps each notification type to its preference group.
# Used in NotificationService to look up which group's preferences to check.
NOTIFICATION_TYPE_GROUP_MAP = {
    NotificationType.PAYMENT_SUCCESS: NotificationGroup.PAYMENTS,
    NotificationType.PAYMENT_FAILED: NotificationGroup.PAYMENTS,
    NotificationType.WALLET_TOPUP: NotificationGroup.WALLET,
    NotificationType.SUBSCRIPTION_EXPIRING: NotificationGroup.SUBSCRIPTIONS,
    NotificationType.SUBSCRIPTION_EXPIRED: NotificationGroup.SUBSCRIPTIONS,
    NotificationType.SUBSCRIPTION_ACTIVATED: NotificationGroup.SUBSCRIPTIONS,
}

# Descriptions are static metadata — they describe what each group covers.
# They are never stored in the database. The API merges these with the database
# values at read time so the frontend always knows what each group means.
NOTIFICATION_GROUP_DESCRIPTIONS = {
    NotificationGroup.PAYMENTS: 'Notifications for payment success and payment failure events.',
    NotificationGroup.SUBSCRIPTIONS: 'Notifications for subscription activation, expiry warnings, and expired subscriptions.',
    NotificationGroup.WALLET: 'Notifications for wallet top-up events.',
}