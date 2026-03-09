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

# Maps each notification type to its group
NOTIFICATION_TYPE_GROUP_MAP = {
    NotificationType.PAYMENT_SUCCESS: NotificationGroup.PAYMENTS,
    NotificationType.PAYMENT_FAILED: NotificationGroup.PAYMENTS,
    NotificationType.WALLET_TOPUP: NotificationGroup.WALLET,
    NotificationType.SUBSCRIPTION_EXPIRING: NotificationGroup.SUBSCRIPTIONS,
    NotificationType.SUBSCRIPTION_EXPIRED: NotificationGroup.SUBSCRIPTIONS,
    NotificationType.SUBSCRIPTION_ACTIVATED: NotificationGroup.SUBSCRIPTIONS,
}

DEFAULT_NOTIFICATION_PREFERENCES = {
    NotificationGroup.PAYMENTS: {'email': True, 'push': True},
    NotificationGroup.SUBSCRIPTIONS: {'email': True, 'push': True},
    NotificationGroup.WALLET: {'email': True, 'push': True},
}