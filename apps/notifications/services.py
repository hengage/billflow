import re
from django.contrib.auth import get_user_model
from .models import Notification, UserNotificationPreferences
from .constants import (
    NotificationType,
    NotificationChannel,
    NotificationGroup,
    NOTIFICATION_TYPE_GROUP_MAP,
)
from .services.email_providers import get_email_provider
from .services.template_renderer import TemplateRenderer

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
    def _dispatch_email(cls, user, prefs, notification_type, subject, template_name, context):
        """Render HTML template and dispatch via configured email provider."""
        if not cls._should_send_email(prefs, notification_type):
            return

        html_content = TemplateRenderer.render(template_name, context)
        plain_preview = cls._extract_preview(html_content)
        cls._log(user, notification_type, NotificationChannel.EMAIL, plain_preview)

        provider = get_email_provider()
        provider.send(
            to=[user.email],
            subject=subject,
            html_content=html_content,
            tags={'notification_type': notification_type, 'user_id': str(user.id)}
        )

    @staticmethod
    def _extract_preview(html_content, length=200):
        """Extract plain text preview from HTML for logging."""
        text = re.sub(r'<[^>]+>', ' ', html_content)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:length] + '...' if len(text) > length else text

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
    def _dispatch(cls, user, notification_type, subject, template_name, context):
        """Central dispatch - handles email (templated) and push."""
        prefs = cls._get_preferences(user)
        cls._dispatch_email(user, prefs, notification_type, subject, template_name, context)
        plain_message = cls._extract_preview(TemplateRenderer.render(template_name, context), 100)
        cls._dispatch_push(user, prefs, notification_type, plain_message)

    # -------------------------------------------------------------------------
    # Public methods — one per notification event
    # -------------------------------------------------------------------------

    @classmethod
    def send_payment_success(cls, user, payment):
        """Payment succeeded notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.PAYMENT_SUCCESS,
            subject='Payment Successful',
            template_name='payment_success',
            context={
                'user': user,
                'payment': payment,
                'amount': str(payment.amount),
                'currency': payment.currency,
                'reference': str(payment.reference),
            }
        )

    @classmethod
    def send_payment_failed(cls, user, payment):
        """Payment failed notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.PAYMENT_FAILED,
            subject='Payment Failed',
            template_name='payment_failed',
            context={
                'user': user,
                'payment': payment,
                'amount': str(payment.amount),
                'currency': payment.currency,
                'reference': str(payment.reference),
            }
        )

    @classmethod
    def send_wallet_topup(cls, user, amount):
        """Wallet top-up notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.WALLET_TOPUP,
            subject='Wallet Top-Up Confirmed',
            template_name='wallet_topup',
            context={
                'user': user,
                'amount': str(amount),
            }
        )

    @classmethod
    def send_subscription_activated(cls, user, plan):
        """Subscription activated notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.SUBSCRIPTION_ACTIVATED,
            subject='Subscription Activated',
            template_name='subscription_activated',
            context={
                'user': user,
                'plan': plan,
                'plan_name': plan.name,
            }
        )

    @classmethod
    def send_subscription_expiring(cls, user, plan, end_date):
        """Subscription expiring soon notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.SUBSCRIPTION_EXPIRING,
            subject='Subscription Expiring Soon',
            template_name='subscription_expiring',
            context={
                'user': user,
                'plan': plan,
                'plan_name': plan.name,
                'end_date': end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else str(end_date),
            }
        )

    @classmethod
    def send_subscription_expired(cls, user, plan):
        """Subscription expired notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.SUBSCRIPTION_EXPIRED,
            subject='Subscription Expired',
            template_name='subscription_expired',
            context={
                'user': user,
                'plan': plan,
                'plan_name': plan.name,
            }
        )

    @classmethod
    def send_subscription_renewed(cls, user, subscription, payment):
        """Subscription auto-renewed notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.SUBSCRIPTION_RENEWED,
            subject='Subscription Renewed',
            template_name='subscription_renewed',
            context={
                'user': user,
                'subscription': subscription,
                'payment': payment,
                'plan_name': subscription.plan.name,
                'amount': str(payment.amount),
                'currency': payment.currency,
                'end_date': subscription.end_date_utc.strftime('%Y-%m-%d'),
            }
        )

    @classmethod
    def send_renewal_failed(cls, user, subscription, attempts_remaining):
        """Auto-renewal failed notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.RENEWAL_FAILED,
            subject='Renewal Failed - Action Required',
            template_name='renewal_failed',
            context={
                'user': user,
                'subscription': subscription,
                'plan_name': subscription.plan.name,
                'attempts_remaining': attempts_remaining,
                'final_attempt': attempts_remaining == 0,
            }
        )

    @classmethod
    def send_subscription_cancelled(cls, user, plan):
        """Subscription cancelled notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.SUBSCRIPTION_CANCELLED,
            subject='Subscription Cancelled',
            template_name='subscription_cancelled',
            context={
                'user': user,
                'plan': plan,
                'plan_name': plan.name,
            }
        )

    @classmethod
    def send_plan_switched(cls, user, old_plan, new_plan, subscription):
        """Plan switched notification."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.PLAN_SWITCHED,
            subject='Plan Switched Successfully',
            template_name='plan_switched',
            context={
                'user': user,
                'old_plan': old_plan,
                'new_plan': new_plan,
                'subscription': subscription,
                'old_plan_name': old_plan.name,
                'new_plan_name': new_plan.name,
                'end_date': subscription.end_date_utc.strftime('%Y-%m-%d'),
            }
        )

    @classmethod
    def send_welcome(cls, user):
        """Welcome email for new users."""
        cls._dispatch(
            user=user,
            notification_type=NotificationType.WELCOME,
            subject='Welcome to BillFlow',
            template_name='welcome',
            context={
                'user': user,
            }
        )