from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.infra.outbox import OutboxDrainer, recover_stale_entries
from apps.infra.models import Outbox
from .services.notification_service import NotificationService
from utils.celery_helpers import backoff_with_jitter, MAX_RETRIES

User = get_user_model()

# Drainer configuration
DOMAIN = 'notifications'
BATCH_SIZE = 50
LOCK_KEY = 'outbox:drain:notifications:lock'


@shared_task(name=settings.TASK_NOTIFICATION_DRAIN_OUTBOX, queue=settings.TASK_QUEUE_NOTIFICATIONS)
def drain_notification_outbox():
    """
    Poll outbox for pending notifications and enqueue to Celery workers.
    
    Uses OutboxDrainer for exactly-once processing with distributed locking.
    """
    def enqueue_notification(entry):
        """Callback to enqueue a single notification to Celery."""
        payload = entry.payload
        send_notification_from_outbox.delay(
            outbox_id=entry.id,
            user_id=payload['user_id'],
            email=payload['email'],
            notification_type=payload['notification_type'],
            subject=payload['subject'],
            template_name=payload['template_name'],
            context=payload['context'],
        )
    
    drainer = OutboxDrainer(
        domain=DOMAIN,
        batch_size=BATCH_SIZE,
        enqueue_func=enqueue_notification,
        lock_key=LOCK_KEY,
    )
    return drainer.drain()


@shared_task(
    name=settings.TASK_NOTIFICATION_SEND_FROM_OUTBOX,
    queue=settings.TASK_QUEUE_NOTIFICATIONS,
    bind=True,
    max_retries=MAX_RETRIES,
)
def send_notification_from_outbox(self, outbox_id, user_id, email, notification_type,
                                   subject, template_name, context):
    """
    Worker task: send email and push notification from outbox entry.
    
    Calls NotificationService._dispatch which:
    - Checks user preferences (email/push enabled)
    - Renders template and sends email via provider
    - Logs and sends push notification
    
    Args:
        outbox_id: Outbox entry ID (for idempotency)
        user_id: Recipient user UUID
        email: Recipient email
        notification_type: Notification type enum
        subject: Email subject
        template_name: Template key
        context: Template context dict
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        # Mark as sent to avoid retrying for deleted users
        Outbox.objects.filter(id=outbox_id).update(status=Outbox.Status.SENT)
        return {'status': 'user_not_found', 'outbox_id': outbox_id}
    
    try:
        # Send via NotificationService (checks preferences, sends email + push)
        NotificationService._dispatch(
            user=user,
            notification_type=notification_type,
            subject=subject,
            template_name=template_name,
            context=context,
        )
        
        # Mark outbox entry as sent
        Outbox.objects.filter(id=outbox_id).update(status=Outbox.Status.SENT)
        
        return {'status': 'sent', 'outbox_id': outbox_id}
        
    except Exception as exc:
        # Log error, update outbox with error info
        Outbox.objects.filter(id=outbox_id).update(
            last_error=f'{type(exc).__name__}: {str(exc)}'[:500]
        )
        raise self.retry(exc=exc, countdown=backoff_with_jitter(self.request.retries))


@shared_task(
    name=settings.TASK_NOTIFICATION_RECOVER_STALE,
    queue=settings.TASK_QUEUE_NOTIFICATIONS,
)
def recover_stale_notification_entries():
    """
    Recovery task: detect and alert on stale pending notification entries.
    
    Should run periodically (e.g., every 30 minutes) via celery-beat.
    """
    return recover_stale_entries(domain=DOMAIN, stale_threshold_minutes=30)
