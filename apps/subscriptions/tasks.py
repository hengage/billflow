import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from celery import shared_task

from utils.celery_helpers import backoff_with_jitter, MAX_RETRIES

from django.db.models import Q

from .models import Subscription

logger = logging.getLogger(__name__)


@shared_task(name="subscriptions.dispatch_expiries")
def dispatch_subscription_expiries():
    """
    Finds ACTIVE subscriptions past their end_date and fans them out to workers.
    Scales to 50k+ because it only pulls IDs, not full objects.
    """
    now = timezone.now()

    # Only select the ID to keep the initial query extremely light
    expired_ids = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        end_date__lte=now
    ).values_list('id', flat=True).iterator()

    count = 0
    for sub_id in expired_ids:
        # Fan-out: each expiry gets its own task in the queue
        process_single_expiry.delay(str(sub_id))
        count += 1

    if count > 0:
        logger.info(f"Dispatched {count} subscriptions for expiry.")


@shared_task(bind=True, max_retries=MAX_RETRIES)
def process_single_expiry(self, subscription_id):
    """
    Handles the actual side-effects of expiry.
    Uses database-level locking for concurrency safety.
    """
    from .services import SubscriptionService
    from notifications.services import NotificationService

    try:
        with transaction.atomic():
            # If another worker is already processing this row, it skips it (skip_locked=True).
            subscription = Subscription.objects.select_for_update(skip_locked=True).filter(
                id=subscription_id,
                status=Subscription.Status.ACTIVE
            ).select_related('user', 'plan').first()

            if not subscription:
                # Either already expired by another worker or not found
                return

            SubscriptionService.expire_subscription(subscription)

            transaction.on_commit(lambda: NotificationService.send_subscription_expired(
                user=subscription.user,
                plan=subscription.plan
            ))

            logger.info(f"Successfully expired subscription {subscription_id}")

    except Exception as exc:
        logger.error(f"Error expiring sub {subscription_id}: {exc}")
        raise self.retry(exc=exc, countdown=backoff_with_jitter(self.request.retries))


@shared_task(name="subscriptions.dispatch_renewals")
def dispatch_renewal_attempts(batch_size=500):
    """
    Runs hourly. Finds subscriptions expiring in 24-48h with:
    - Status ACTIVE (RENEWED ones already handled)
    - Under 3 renewal attempts
    - Respects cooldown: 6h after 1st attempt, 24h after 2nd

    Max 500 renewals per run — remaining process next hour.
    """
    now = timezone.now()
    window_start = now + timedelta(hours=24)
    window_end = now + timedelta(hours=48)

    renewing = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        end_date_utc__gte=window_start,
        end_date_utc__lte=window_end,
        renewal_attempts__lt=3,
    ).exclude(
        Q(renewal_attempts=1, last_renewal_attempt_at__gte=now - timedelta(hours=6)) |
        Q(renewal_attempts=2, last_renewal_attempt_at__gte=now - timedelta(hours=24))
    )[:batch_size]

    count = 0
    for sub_id in renewing:
        attempt_auto_renewal.delay(str(sub_id))
        count += 1

    if count > 0:
        logger.info(f"Dispatched {count} renewals for attempt")
    if count == batch_size:
        logger.info("Renewal batch limit reached, remaining will process next hour")


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    queue='renewals',
    rate_limit='5/s',
)
def attempt_auto_renewal(self, subscription_id):
    """
    Attempts to charge stored payment method and renew subscription.

    - Payment declined: Processor handles, no Celery retry
    - Transient error: Celery retry with same idempotency key
    - Success: Task ends, webhook completes renewal
    """
    from .services import RenewalProcessor

    try:
        RenewalProcessor(subscription_id).execute()
    except Exception as exc:
        logger.error(f"Renewal error for {subscription_id}: {exc}")
        raise self.retry(exc=exc, countdown=backoff_with_jitter(self.request.retries))
