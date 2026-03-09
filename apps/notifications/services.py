from django.contrib.auth import get_user_model
from .models import Notification
from .constants import (
    NotificationType,
    NotificationChannel,
    NotificationGroup,
    NOTIFICATION_TYPE_GROUP_MAP,
    DEFAULT_NOTIFICATION_PREFERENCES,
)
from .tasks import send_email_task

User = get_user_model()


class NotificationService:

    @staticmethod
    def _get_group_prefs(user, notification_type):
        """
        Given a notification type, find its group and return
        the user's preferences for that group.
        Falls back to DEFAULT_NOTIFICATION_PREFERENCES if the user
        hasn't set preferences yet (e.g new accounts).
        """
        group = NOTIFICATION_TYPE_GROUP_MAP.get(notification_type)
        user_prefs = user.notification_preferences
        return user_prefs.get(
            group,
            DEFAULT_NOTIFICATION_PREFERENCES.get(group, {'email': True, 'push': False})
        )

    @staticmethod
    def _log(user, notification_type, channel, message):
        return Notification.objects.create(
            user=user,
            type=notification_type,
            channel=channel,
            message=message,
        )

    @classmethod
    def _dispatch_email(cls, user, notification_type, subject, message, html_message=None):
        prefs = cls._get_group_prefs(user, notification_type)
        if not prefs.get('email', True):
            return
        cls._log(user, notification_type, NotificationChannel.EMAIL, message)
        send_email_task.delay(
            user_id=str(user.id),
            subject=subject,
            message=message,
            html_message=html_message,
        )

    @classmethod
    def _dispatch_push(cls, user, notification_type, message):
        # Push notifications wired up when React frontend is built
        prefs = cls._get_group_prefs(user, notification_type)
        if not prefs.get('push', False):
            return
        cls._log(user, notification_type, NotificationChannel.PUSH, message)
        # push_task.delay(user_id=str(user.id), message=message)

    @classmethod
    def _dispatch(cls, user, notification_type, subject, message, html_message=None):
        """
        Central dispatch — sends both email and push based on user preferences.
        All public methods call this instead of _dispatch_email directly.
        """
        cls._dispatch_email(user, notification_type, subject, message, html_message)
        cls._dispatch_push(user, notification_type, message)

    # -------------------------------------------------------------------------
    # Public methods
    # -------------------------------------------------------------------------

    @classmethod
    def send_payment_success(cls, user, payment):
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your payment of {payment.amount} {payment.currency} was successful.\n'
            f'Reference: {payment.reference}\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.PAYMENT_SUCCESS, 'Payment Successful', message)

    @classmethod
    def send_payment_failed(cls, user, payment):
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your payment of {payment.amount} {payment.currency} failed.\n'
            f'Reference: {payment.reference}\n\n'
            f'Please try again or contact support.'
        )
        cls._dispatch(user, NotificationType.PAYMENT_FAILED, 'Payment Failed', message)

    @classmethod
    def send_wallet_topup(cls, user, amount):
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your wallet has been credited with {amount} NGN.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.WALLET_TOPUP, 'Wallet Top-Up Confirmed', message)

    @classmethod
    def send_subscription_activated(cls, user, plan):
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your subscription to the {plan.name} plan has been activated.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.SUBSCRIPTION_ACTIVATED, 'Subscription Activated', message)

    @classmethod
    def send_subscription_expiring(cls, user, plan, end_date):
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your {plan.name} subscription expires on {end_date}.\n'
            f'Renew now to avoid interruption.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.SUBSCRIPTION_EXPIRING, 'Subscription Expiring Soon', message)

    @classmethod
    def send_subscription_expired(cls, user, plan):
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your {plan.name} subscription has expired.\n'
            f'Subscribe again to continue using BillFlow.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.SUBSCRIPTION_EXPIRED, 'Subscription Expired', message)
