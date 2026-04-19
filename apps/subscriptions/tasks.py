import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from celery import shared_task

from django.conf import settings
from utils.celery_helpers import backoff_with_jitter, MAX_RETRIES

from django.db.models import Q

from .models import Subscription

logger = logging.getLogger(__name__)


@shared_task(name=settings.TASK_SUBSCRIPTION_DISPATCH_EXPIRIES)
def dispatch_subscription_expiries():
    """
    Finds ACTIVE subscriptions past their end_date and fans them out to workers.
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


@shared_task(name=settings.TASK_SUBSCRIPTION_DISPATCH_RENEWALS)
def dispatch_renewal_attempts(batch_size=500):
    """
    Runs every 2 minutes (testing). Finds subscriptions expiring in 48-72h with:
    - Status ACTIVE (RENEWED ones already handled)
    - Under 3 renewal attempts
    - Respects cooldown: 6h after 1st attempt, 24h after 2nd

    Max 500 renewals per run — remaining process next hour.
    """
    logger.info("[dispatch_renewals] Task started")
    now = timezone.now()
    window_start = now + timedelta(hours=48)
    window_end = now + timedelta(hours=72)
    logger.info(f"[dispatch_renewals] Query window: {window_start} to {window_end}")

    renewing = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        end_date_utc__gte=window_start,
        end_date_utc__lte=window_end,
        renewal_attempts__lt=3,
    ).exclude(
        Q(renewal_attempts=1, last_renewal_attempt_at__gte=now - timedelta(hours=6)) |
        Q(renewal_attempts=2, last_renewal_attempt_at__gte=now - timedelta(hours=24))
    )[:batch_size]

    # Force evaluation to get count and log details
    renewing_list = list(renewing)
    count = len(renewing_list)
    logger.info(f"[dispatch_renewals] Found {count} subscriptions to renew")

    for sub in renewing_list:
        logger.info(f"[dispatch_renewals] Dispatching renewal for sub {sub.id}, user {sub.user_id}, ends {sub.end_date_utc}")
        attempt_auto_renewal.delay(str(sub.id))

    if count > 0:
        logger.info(f"[dispatch_renewals] Dispatched {count} renewals")
    else:
        logger.info("[dispatch_renewals] No subscriptions found for renewal")
    if count == batch_size:
        logger.info("[dispatch_renewals] Batch limit reached")


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    name=settings.TASK_SUBSCRIPTION_ATTEMPT_RENEWAL,
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

    logger.info(f"[attempt_auto_renewal] Task started for subscription {subscription_id}, retry {self.request.retries}")

    try:
        processor = RenewalProcessor(subscription_id)
        logger.info(f"[attempt_auto_renewal] Processor initialized for {subscription_id}")
        result = processor.execute()
        logger.info(f"[attempt_auto_renewal] Processor.execute() completed for {subscription_id}, result: {result}")
    except Exception as exc:
        logger.error(f"[attempt_auto_renewal] Renewal error for {subscription_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=backoff_with_jitter(self.request.retries))
