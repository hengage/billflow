import re
from django.contrib.auth import get_user_model
from apps.infra.models import Outbox
from ..models import Notification, UserNotificationPreferences
from ..constants import (
    NotificationType,
    NotificationChannel,
    NotificationGroup,
    NOTIFICATION_TYPE_GROUP_MAP,
)
from .email_providers import get_email_provider
from .template_renderer import TemplateRenderer

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
    def enqueue_to_outbox(cls, user, notification_type, subject, template_name, context):
        """
        Enqueue notification to outbox for async processing.
        
        Writes to outbox (atomic with business transaction).
        Drainer polls and enqueues to Celery worker.
        Worker calls _dispatch to send email + push based on user preferences.
        
        Args:
            user: User instance
            notification_type: NotificationType enum value
            subject: Email subject
            template_name: Template key for rendering
            context: Dict with template variables
        """
        Outbox.objects.create(
            domain='notifications',
            event_type=notification_type,
            payload={
                'user_id': str(user.id),
                'email': user.email,
                'notification_type': notification_type,
                'subject': subject,
                'template_name': template_name,
                'context': context,
            }
        )

    @classmethod
    def _dispatch(cls, user, notification_type, subject, template_name, context):
        """
        Worker-facing method: handles email (templated) and push.
        
        Checks user preferences and sends to enabled channels.
        Called by send_notification_from_outbox Celery task.
        """
        prefs = cls._get_preferences(user)
        cls._dispatch_email(user, prefs, notification_type, subject, template_name, context)
        plain_message = cls._extract_preview(TemplateRenderer.render(template_name, context), 100)
        cls._dispatch_push(user, prefs, notification_type, plain_message)
