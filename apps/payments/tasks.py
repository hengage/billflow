import logging
import random
from celery import shared_task, Task
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

MAX_RETRIES = 3
BASE_DELAY = 60
MAX_DELAY = 3600


def _backoff_with_jitter(retry_number):
    """
    Calculates retry delay using exponential backoff with full jitter.

    Full jitter spreads retries randomly across the backoff window, 
    reducing peak load on the server.

    Formula: random(0, min(cap, base * 2^n))
    Reference: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
    """
    exponential = BASE_DELAY * (2 ** retry_number)
    capped = min(MAX_DELAY, exponential)
    return random.uniform(0, capped)

class WebhookTaskBase(Task):
    """
    Custom base class for webhook processing tasks.
    Provides the on_failure hook that runs when max_retries is exhausted.
    """
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Called by Celery automatically after the final retry is exhausted.
        This is the DLQ handler — it marks the webhook as permanently failed
        so the reconciliation job stops requeuing it, and logs a critical
        alert for investigation.
        """
        from payments.models import WebhookLog

        log_id = kwargs.get('webhook_log_id') or (args[0] if args else None)

        if log_id:
            try:
                WebhookLog.objects.filter(id=log_id).update(
                    permanently_failed=True,
                    failure_reason=(
                        f'Exhausted {self.max_retries} retries. '
                        f'Final error: {str(exc)}\n'
                        f'Traceback:\n{str(einfo)}'
                    ),
                )
            except Exception as update_exc:
                logger.error(f'Failed to mark webhook as permanently failed | log={log_id} | error={str(update_exc)}')

        logger.critical(
            f'WEBHOOK PERMANENTLY FAILED — requires manual review | '
            f'log_id={log_id} | task_id={task_id} | error={str(exc)}'
        )
        # TODO: Fire alert to PagerDuty here when alerting is configured.

@shared_task(
    bind=True,
    base=WebhookTaskBase,
    max_retries=MAX_RETRIES,
    queue='webhooks',
    acks_late=True,           # don't acknowledge the task until it completes —
                              # if the worker crashes, the task goes back to the queue
    reject_on_worker_lost=True,  # explicitly reject (not ack) if worker dies mid-task
)
def process_webhook_event(self, webhook_log_id, provider):
    """
    Processes a webhook event from Payment providers.

    This task is queued immediately after the webhook arrives and the raw
    payload is written to WebhookLog. 

    All processing logic is delegated to WebhookHandler — this task only
    handles retry semantics and queue routing.
    """
    from payments.services.webhook_handler import WebhookHandler

    try:
        WebhookHandler.process(webhook_log_id, provider)
    except Exception as exc:
        logger.error(
            f'Webhook processing failed | '
            f'log={webhook_log_id} | attempt={self.request.retries + 1} | '
            f'error={str(exc)}'
        )
        delay = _backoff_with_jitter(self.request.retries)
        raise self.retry(exc=exc, countdown=delay)


@shared_task
def reconcile_unprocessed_webhooks():
    """
    Finds WebhookLog records that were never processed and requeues them.
    
    This is the safety net for the gap between WebhookLog being committed
    and the Celery task being durably picked up by a worker. It runs every
    10 minutes via Celery Beat and handles any logs that fell through.

    Reference: https://brandur.org/job-drain
    """
    from django.utils import timezone
    from datetime import timedelta
    from payments.models import WebhookLog

    threshold = timezone.now() - timedelta(minutes=10)
    stuck_logs = WebhookLog.objects.filter(
        processed=False,
        permanently_failed=False,
        received_at__lt=threshold,
    )

    for log in stuck_logs:
        process_webhook_event.delay(
            webhook_log_id=str(log.id),
            provider=log.provider,
        )
        logger.info(
            f'Requeued stuck webhook | log={log.id} | '
            f'provider={log.provider} | event={log.event_type}'
        )

@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    queue='notifications',
    acks_late=True,
    reject_on_worker_lost=True,
)
def send_payment_success_notification(self, user_id, payment_id):
    from payments.models import Payment
    from notifications.services import NotificationService

    try:
        user = User.objects.get(id=user_id)
        payment = Payment.objects.get(id=payment_id)
        NotificationService.send_payment_success(user, payment)
    except (User.DoesNotExist, Payment.DoesNotExist):
        return
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff_with_jitter(self.request.retries))


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    queue='notifications',
    acks_late=True,
    reject_on_worker_lost=True,
)
def send_payment_failed_notification(self, user_id, payment_id):
    from payments.models import Payment
    from notifications.services import NotificationService

    try:
        user = User.objects.get(id=user_id)
        payment = Payment.objects.get(id=payment_id)
        NotificationService.send_payment_failed(user, payment)
    except (User.DoesNotExist, Payment.DoesNotExist):
        return
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff_with_jitter(self.request.retries))