import logging
from datetime import timedelta
from django.db import transaction
from django.core.cache import cache
from django.utils import timezone

from .models import Plan, Subscription
from .constants import (
    USER_SUBSCRIPTION_CACHE_KEY_PREFIX,
    USER_SUBSCRIPTION_CACHE_TTL,
)

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    All subscription lifecycle logic lives here.
    """

    @staticmethod
    def get_active_subscription(user):
        """
        Returns the user's active subscription or None.
        Checks cache first — falls back to database.
        Cache is invalidated by post_save signal on Subscription.
        """
        cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{user.id}'
        cached = cache.get(cache_key)

        if cached is not None:
            return cached

        subscription = Subscription.objects.filter(
            user=user,
            status=Subscription.Status.ACTIVE,
        ).select_related('plan').first()

        cache.set(cache_key, subscription, timeout=USER_SUBSCRIPTION_CACHE_TTL)
        return subscription

    @staticmethod
    def activate(user, plan_id, payment=None):
        """
        Activates a subscription for the user.
        Called by:
            - WebhookHandler after a successful direct payment
            - SubscriptionService.subscribe_via_wallet() for wallet payments

        Args:
            user: User instance
            plan_id: UUID of the Plan to subscribe to
            payment: Payment instance (None for wallet payments)

        Returns:
            Subscription instance
        """
        try:
            plan = Plan.objects.get(id=plan_id, is_active=True)
        except Plan.DoesNotExist:
            raise ValueError(f'Plan {plan_id} does not exist or is inactive.')

        with transaction.atomic():
            existing = Subscription.objects.select_for_update().filter(
                user=user,
                status=Subscription.Status.ACTIVE,
            ).first()

            if existing:
                raise ValueError(
                    f'You already have an active {existing.plan.name} subscription '
                    f'expiring on {existing.end_date}. '
                    f'Cancel it before subscribing to a new plan.'
                )

            today = timezone.now()

            if billing_cycle == Subscription.BillingCycle.MONTHLY:
                end_date = today + timedelta(days=30)
                amount = plan.monthly_price_ngn
            else:
                end_date = today + timedelta(days=365)
                amount = plan.yearly_price_ngn

            subscription = Subscription.objects.create(
                user=user,
                plan=plan,
                billing_cycle=billing_cycle,
                amount_paid=amount,
                status=Subscription.Status.ACTIVE,
                start_date_utc=today,
                end_date_utc=end_date,
                payment=payment,
            )

        cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{user.id}'
        cache.delete(cache_key)

        return subscription

    @staticmethod
    def subscribe_via_wallet(user, plan):
        """
        Subscribes a user to a plan by deducting from their wallet.
        This is the wallet payment flow — no external provider involved.

        The deduction and subscription creation happen in the same
        transaction.atomic() block in WalletService.deduct() — if either
        fails, both roll back. We activate the subscription here, after
        the deduction succeeds.

        Args:
            user: User instance
            plan: Plan instance

        Returns:
            Subscription instance

        Raises:
            ValueError if wallet balance is insufficient
        """
        from wallets.service import WalletService
        import uuid

        reference = str(uuid.uuid4())

        # WalletService.deduct() handles the atomic balance check and deduction.
        # It raises ValueError if balance is insufficient — we let that propagate
        # to the view which returns a 400 to the client.
        WalletService.deduct(
            user=user,
            amount=plan.price_ngn,
            reference=reference,
        )

        # Deduction succeeded — activate the subscription.
        # No payment record for wallet subscriptions — the WalletTransaction
        # is the financial record for this flow.
        subscription = SubscriptionService.activate(
            user=user,
            plan_id=str(plan.id),
            payment=None,
        )

        return subscription

    @staticmethod
    def cancel(user):
        """
        Cancels the user's active subscription.

        Args:
            user: User instance

        Returns:
            Cancelled Subscription instance

        Raises:
            ValueError if no active subscription exists
        """
        with transaction.atomic():
            subscription = Subscription.objects.select_for_update().filter(
                user=user,
                status=Subscription.Status.ACTIVE,
            ).first()

            if not subscription:
                raise ValueError('No active subscription found.')

            subscription.status = Subscription.Status.CANCELLED
            subscription.save(update_fields=['status'])

        # Invalidate cache
        cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{user.id}'
        cache.delete(cache_key)

        logger.info(
            f'Subscription cancelled | user={user.id} | '
            f'subscription={subscription.id}'
        )
        return subscription

    @staticmethod
    def expire_subscription(subscription):
        """
        Marks a subscription as expired.
        Called by the check_expired_subscriptions Celery task.
        """
        subscription.status = Subscription.Status.EXPIRED
        subscription.save(update_fields=['status'])

        cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{subscription.user_id}'
        cache.delete(cache_key)

        logger.info(
            f'Subscription expired | user={subscription.user_id} | '
            f'subscription={subscription.id}'
        )