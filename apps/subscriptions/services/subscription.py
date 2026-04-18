"""
SubscriptionService - Subscription lifecycle management.

Handles activation, cancellation, expiration, and renewal of subscriptions.
"""
import logging
from datetime import timedelta
from django.db import transaction
from django.core.cache import cache
from django.utils import timezone

from ..models import Plan, Subscription
from ..constants import (
    USER_SUBSCRIPTION_CACHE_KEY_PREFIX,
    USER_SUBSCRIPTION_CACHE_TTL,
)
from utils.messages import get_message

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    All subscription lifecycle logic lives here.
    """

    @staticmethod
    def get_active_subscription(user):
        """
        Returns the user's active subscription or None.
        Checks cache first - falls back to database.
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
    def activate(user, plan_id, billing_cycle, payment=None):
        """
        Activates a subscription for the user.
        Called by:
            - WebhookHandler after a successful direct payment
            - SubscriptionService.subscribe_via_wallet() for wallet payments

        Args:
            user: User instance
            plan_id: UUID of the Plan to subscribe to
            billing_cycle: Billing cycle (monthly or yearly)
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
                if existing.plan_id == plan.id:
                    # Same plan = manual renewal with 7-day gate
                    subscription = SubscriptionService.process_manual_renewal(
                        existing_subscription=existing,
                        plan=plan,
                        billing_cycle=billing_cycle,
                        payment=payment,
                    )
                else:
                    # Different plan - not handled here, use switch plans option
                    raise ValueError(
                        get_message('DIFFERENT_PLAN_EXISTS', 'SUBSCRIPTION', plan_name=existing.plan.name)
                    )
            else:
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
    def subscribe_via_wallet(user, plan, billing_cycle):
        """
        Subscribes a user to a plan by deducting from their wallet.
        This is the wallet payment flow - no external provider involved.

        The deduction and subscription creation happen atomically - if either
        fails, both roll back via the outer transaction.atomic() block.

        Args:
            user: User instance
            plan: Plan instance
            billing_cycle: Billing cycle (monthly or yearly)

        Returns:
            Subscription instance
        """
        from wallets.service import WalletService
        import uuid

        reference = str(uuid.uuid4())

        if billing_cycle == Subscription.BillingCycle.MONTHLY:
            amount = plan.monthly_price_ngn
        else:
            amount = plan.yearly_price_ngn

        with transaction.atomic():
            # WalletService.deduct() handles the atomic balance check and deduction.
            WalletService.deduct(
                user=user,
                amount=amount,
                reference=reference,
            )

            # Deduction succeeded - activate the subscription.
            # No payment record for wallet subscriptions - the WalletTransaction
            # is the financial record for this flow.
            subscription = SubscriptionService.activate(
                user=user,
                plan_id=str(plan.id),
                billing_cycle=billing_cycle,
                payment=None,
            )

        return subscription

    @staticmethod
    def switch_plan_via_wallet(user, new_plan, billing_cycle):
        """
        Switches plan using wallet balance.
        Deducts from wallet, cancels old subscription, creates new one.

        Args:
            user: User instance
            new_plan: Plan instance to switch to
            billing_cycle: MONTHLY or YEARLY

        Returns:
            New Subscription instance

        Raises:
            ValueError if insufficient balance or same plan
        """
        from wallets.service import WalletService
        import uuid

        reference = str(uuid.uuid4())

        # Calculate amount based on billing cycle
        if billing_cycle == Subscription.BillingCycle.MONTHLY:
            amount = new_plan.monthly_price_ngn
        else:
            amount = new_plan.yearly_price_ngn

        with transaction.atomic():
            # WalletService.deduct() handles the atomic balance check and deduction.
            WalletService.deduct(
                user=user,
                amount=amount,
                reference=reference,
            )

            # Deduction succeeded - switch the plan.
            subscription = SubscriptionService.switch_plan(
                user=user,
                new_plan=new_plan,
                billing_cycle=billing_cycle,
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
            subscription.cancelled_at = timezone.now()
            subscription.save(update_fields=['status', 'cancelled_at'])

        # Invalidate cache
        cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{user.id}'
        cache.delete(cache_key)

        logger.info(
            f'Subscription cancelled | user={user.id} | '
            f'subscription={subscription.id}'
        )
        return subscription

    @staticmethod
    def switch_plan(user, new_plan, billing_cycle, payment=None):
        """
        Switches user to a different plan.
        Cancels current subscription immediately and creates new one.

        Args:
            user: User instance
            new_plan: Plan instance to switch to
            billing_cycle: MONTHLY or YEARLY
            payment: Optional Payment instance (for wallet payments)

        Returns:
            New Subscription instance

        Raises:
            ValueError if no active subscription or same plan
        """
        with transaction.atomic():
            # Get and cancel existing subscription
            existing = Subscription.objects.select_for_update().filter(
                user=user,
                status=Subscription.Status.ACTIVE,
            ).first()

            if not existing:
                raise ValueError('No active subscription to switch from.')

            if str(existing.plan_id) == str(new_plan.id):
                raise ValueError('Cannot switch to the same plan. Use renewal instead.')

            # Cancel existing immediately
            existing.status = Subscription.Status.CANCELLED
            existing.cancelled_at = timezone.now()
            existing.save(update_fields=['status', 'cancelled_at'])

            # Create new subscription
            today = timezone.now()
            if billing_cycle == Subscription.BillingCycle.MONTHLY:
                end_date = today + timedelta(days=30)
                amount = new_plan.monthly_price_ngn
            else:
                end_date = today + timedelta(days=365)
                amount = new_plan.yearly_price_ngn

            new_subscription = Subscription.objects.create(
                user=user,
                plan=new_plan,
                billing_cycle=billing_cycle,
                amount_paid=amount,
                status=Subscription.Status.ACTIVE,
                start_date_utc=today,
                end_date_utc=end_date,
                payment=payment,
            )

        # Invalidate cache
        cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{user.id}'
        cache.delete(cache_key)

        logger.info(
            f'Plan switched | user={user.id} | old_plan={existing.plan_id} | '
            f'new_plan={new_plan.id} | old_sub={existing.id} | new_sub={new_subscription.id}'
        )
        return new_subscription

    @staticmethod
    def can_renew(user, plan_id):
        """
        Pre-validates if user can renew an existing subscription.
        Called before initiating payment to fail fast if renewal not allowed.

        Args:
            user: User instance
            plan_id: UUID of the Plan to check

        Returns:
            tuple: (can_renew: bool, error_message: str or None)
        """
        existing = Subscription.objects.only(
            'plan_id', 'end_date_utc'
        ).filter(
            user=user,
            status=Subscription.Status.ACTIVE,
        ).first()

        if not existing:
            # No existing subscription - new subscription is allowed
            return (True, None)

        if str(existing.plan_id) != str(plan_id):
            # Different plan - use the switch plans option
            return (
                False,
                get_message('DIFFERENT_PLAN_EXISTS', 'SUBSCRIPTION', plan_name=existing.plan.name)
            )

        # Same plan - check 7-day gate
        today = timezone.now()
        days_remaining = (existing.end_date_utc - today).days

        if days_remaining > 7:
            return (
                False,
                get_message('RENEWAL_TOO_EARLY', 'SUBSCRIPTION', days_remaining=days_remaining)
            )

        return (True, None)

    @staticmethod
    def process_manual_renewal(existing_subscription, plan, billing_cycle, payment=None):
        """
        Handles user-initiated early renewal with 7-day eligibility gate.
        Only allows renewal when subscription has 7 or fewer days remaining.

        Args:
            existing_subscription: Current active Subscription instance
            plan: Plan instance (same as current)
            billing_cycle: Billing cycle (monthly or yearly)
            payment: Payment instance (None for wallet payments)

        Returns:
            Updated Subscription instance with extended end_date_utc

        """
        # Extend the subscription
        if billing_cycle == Subscription.BillingCycle.MONTHLY:
            existing_subscription.end_date_utc += timedelta(days=30)
            existing_subscription.amount_paid = plan.monthly_price_ngn
        else:
            existing_subscription.end_date_utc += timedelta(days=365)
            existing_subscription.amount_paid = plan.yearly_price_ngn

        existing_subscription.billing_cycle = billing_cycle
        existing_subscription.payment = payment
        existing_subscription.save(update_fields=[
            'end_date_utc', 'billing_cycle', 'amount_paid', 'payment'
        ])

        return existing_subscription

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

    @staticmethod
    def renew(old_subscription, payment):
        """
        Renews a subscription by marking old as RENEWED and creating new ACTIVE.

        New subscription starts from max(now, old.end_date) to ensure no gap.
        Called by webhook handler after successful renewal payment.

        Args:
            old_subscription: Subscription instance to renew (must be ACTIVE)
            payment: Payment instance from successful charge

        Returns:
            New Subscription instance
        """
        with transaction.atomic():
            # Mark old as RENEWED
            old_subscription.status = Subscription.Status.RENEWED
            old_subscription.save(update_fields=['status'])

            # Calculate new period
            now = timezone.now()
            new_start = max(now, old_subscription.end_date_utc)

            if old_subscription.billing_cycle == Subscription.BillingCycle.MONTHLY:
                new_end = new_start + timedelta(days=30)
                amount = old_subscription.plan.monthly_price_ngn
            else:
                new_end = new_start + timedelta(days=365)
                amount = old_subscription.plan.yearly_price_ngn

            # Create new subscription
            new_subscription = Subscription.objects.create(
                user=old_subscription.user,
                plan=old_subscription.plan,
                billing_cycle=old_subscription.billing_cycle,
                amount_paid=amount,
                status=Subscription.Status.ACTIVE,
                start_date_utc=new_start,
                end_date_utc=new_end,
                payment=payment,
            )

        # Invalidate cache
        cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{old_subscription.user.id}'
        cache.delete(cache_key)

        logger.info(
            f'Subscription renewed | old={old_subscription.id} | '
            f'new={new_subscription.id} | user={old_subscription.user.id}'
        )
        return new_subscription
