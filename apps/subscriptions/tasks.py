import logging
from django.utils import timezone
from django.db import transaction
from celery import shared_task
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


@shared_task(bind=True, max_retries=3)
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
        raise self.retry(exc=exc, countdown=60)
