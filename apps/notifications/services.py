from django.contrib.auth import get_user_model
from .models import Notification, UserNotificationPreferences
from .constants import (
    NotificationType,
    NotificationChannel,
    NotificationGroup,
    NOTIFICATION_TYPE_GROUP_MAP,
)
from .tasks import send_email_task

User = get_user_model()


class NotificationService:

    @staticmethod
    def _get_preferences(user):
        """
        Fetch the user's UserNotificationPreferences record.
        """
        prefs, _ = UserNotificationPreferences.objects.get_or_create(user=user)
        return prefs

    @staticmethod
    def _should_send_email(prefs, notification_type):
        """
        Determine if an email should be sent based on user preferences.
        """
        group = NOTIFICATION_TYPE_GROUP_MAP.get(notification_type)
        if group == NotificationGroup.PAYMENTS:
            return prefs.payments_email
        if group == NotificationGroup.SUBSCRIPTIONS:
            return prefs.subscriptions_email
        if group == NotificationGroup.WALLET:
            return prefs.wallet_email
        return True  # safe default for unknown groups

    @staticmethod
    def _should_send_push(prefs, notification_type):
        """
        Determine if a push notification should be sent based on user preferences.
        """
        group = NOTIFICATION_TYPE_GROUP_MAP.get(notification_type)
        if group == NotificationGroup.PAYMENTS:
            return prefs.payments_push
        if group == NotificationGroup.SUBSCRIPTIONS:
            return prefs.subscriptions_push
        if group == NotificationGroup.WALLET:
            return prefs.wallet_push
        return False  # conservative default for unknown groups

    @staticmethod
    def _log(user, notification_type, channel, message):
        """
        Log a notification to the database.
        """
        return Notification.objects.create(
            user=user,
            type=notification_type,
            channel=channel,
            message=message,
        )

    @classmethod
    def _dispatch_email(cls, user, prefs, notification_type, subject, message, html_message=None):
        """
        Dispatch an email notification if the user has enabled it for this notification type.
        """
        if not cls._should_send_email(prefs, notification_type):
            return
        cls._log(user, notification_type, NotificationChannel.EMAIL, message)
        send_email_task.delay(
            user_id=str(user.id),
            subject=subject,
            message=message,
            html_message=html_message,
        )

    @classmethod
    def _dispatch_push(cls, user, prefs, notification_type, message):
        """
        Dispatch a push notification if the user has enabled it for this notification type.
        """
        if not cls._should_send_push(prefs, notification_type):
            return
        cls._log(user, notification_type, NotificationChannel.PUSH, message)
        # push_task.delay(user_id=str(user.id), message=message)

    @classmethod
    def _dispatch(cls, user, notification_type, subject, message, html_message=None):
        """
        Central dispatch method. Fetches preferences once and passes them
        to both _dispatch_email and _dispatch_push — avoids two DB hits.
        """
        prefs = cls._get_preferences(user)
        cls._dispatch_email(user, prefs, notification_type, subject, message, html_message)
        cls._dispatch_push(user, prefs, notification_type, message)

    # -------------------------------------------------------------------------
    # Public methods — one per notification event
    # -------------------------------------------------------------------------

    @classmethod
    def send_payment_success(cls, user, payment):
        """
        Send a payment success notification to the user.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your payment of {payment.amount} {payment.currency} was successful.\n'
            f'Reference: {payment.reference}\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.PAYMENT_SUCCESS, 'Payment Successful', message)

    @classmethod
    def send_payment_failed(cls, user, payment):
        """
        Send a payment failed notification to the user.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your payment of {payment.amount} {payment.currency} failed.\n'
            f'Reference: {payment.reference}\n\n'
            f'Please try again or contact support.'
        )
        cls._dispatch(user, NotificationType.PAYMENT_FAILED, 'Payment Failed', message)

    @classmethod
    def send_wallet_topup(cls, user, amount):
        """
        Send a wallet top-up notification to the user.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your wallet has been credited with {amount} NGN.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.WALLET_TOPUP, 'Wallet Top-Up Confirmed', message)

    @classmethod
    def send_subscription_activated(cls, user, plan):
        """
        Send a subscription activated notification to the user.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your subscription to the {plan.name} plan has been activated.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.SUBSCRIPTION_ACTIVATED, 'Subscription Activated', message)

    @classmethod
    def send_subscription_expiring(cls, user, plan, end_date):
        """
        Send a subscription expiring notification to the user.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your {plan.name} subscription expires on {end_date}.\n'
            f'Renew now to avoid interruption.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.SUBSCRIPTION_EXPIRING, 'Subscription Expiring Soon', message)

    @classmethod
    def send_subscription_expired(cls, user, plan):
        """
        Send a subscription expired notification to the user.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your {plan.name} subscription has expired.\n'
            f'Subscribe again to continue using BillFlow.\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(user, NotificationType.SUBSCRIPTION_EXPIRED, 'Subscription Expired', message)

    @classmethod
    def send_subscription_renewed(cls, user, subscription, payment):
        """
        Send a subscription renewed notification to the user.
        Called when auto-renewal succeeds.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'Your {subscription.plan.name} subscription has been automatically renewed.\n'
            f'Amount charged: {payment.amount} {payment.currency}\n'
            f'New expiry date: {subscription.end_date_utc}\n\n'
            f'Thank you for using BillFlow.'
        )
        cls._dispatch(
            user,
            NotificationType.SUBSCRIPTION_RENEWED,
            'Subscription Renewed',
            message
        )

    @classmethod
    def send_renewal_failed(cls, user, subscription, attempts_remaining):
        """
        Send a renewal failed notification to the user.
        Called when auto-renewal charge is declined.
        """
        message = (
            f'Hi {user.first_name},\n\n'
            f'We were unable to automatically renew your {subscription.plan.name} subscription.\n'
            f'Please update your payment method to avoid service interruption.\n'
        )
        if attempts_remaining > 0:
            message += f'We will retry {attempts_remaining} more time(s).\n\n'
        else:
            message += 'This was your final retry. Your subscription will expire soon.\n\n'
        message += 'Thank you for using BillFlow.'
        cls._dispatch(
            user,
            NotificationType.RENEWAL_FAILED,
            'Renewal Failed - Action Required',
            message
        )