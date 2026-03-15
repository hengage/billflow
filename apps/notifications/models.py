import uuid
from django.conf import settings
from django.db import models
from .constants import NotificationType, NotificationChannel


class UserNotificationPreferences(models.Model):
    """
    Stores per-user notification preferences as explicit boolean columns.
    
    OneToOneField because each user has exactly one preferences record.
    Created automatically via Django signal when a new User is registered.
    
    Column naming convention: <group>_<channel>
    e.g. payments_email, payments_push, subscriptions_email, etc.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences_obj'
    )

    # Payments group — covers payment_success and payment_failed
    payments_email = models.BooleanField(default=True)
    payments_push = models.BooleanField(default=True)

    # Subscriptions group — covers subscription_activated, subscription_expiring, subscription_expired
    subscriptions_email = models.BooleanField(default=True)
    subscriptions_push = models.BooleanField(default=True)

    # Wallet group — covers wallet_topup
    wallet_email = models.BooleanField(default=True)
    wallet_push = models.BooleanField(default=True)

    def __str__(self):
        return f'Notification preferences for {self.user.email}'


class Notification(models.Model):
    """Audit trail of every notification sent to a user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    type = models.CharField(max_length=50, choices=NotificationType.choices)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.user.email} — {self.type} via {self.channel}'