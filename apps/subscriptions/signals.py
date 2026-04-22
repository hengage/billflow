from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Plan, Subscription
from .constants import (
    PLANS_LIST_CACHE_KEY,
    USER_SUBSCRIPTION_CACHE_KEY_PREFIX,
)


@receiver(post_save, sender=Plan)
@receiver(post_delete, sender=Plan)
def invalidate_plans_cache(sender, **kwargs):
    """
    Invalidates the plans list cache whenever a Plan is created,
    updated, or deleted. This ensures customers always see the
    current plan list without waiting for the TTL to expire.
    """
    cache.delete(PLANS_LIST_CACHE_KEY)


@receiver(post_save, sender=Subscription)
def invalidate_subscription_cache(sender, instance, **kwargs):
    """
    Invalidates the user's subscription cache whenever their
    subscription changes status. Ensures the cached status is
    never stale after a cancellation, expiry, or activation.
    """
    cache_key = f'{USER_SUBSCRIPTION_CACHE_KEY_PREFIX}_{instance.user_id}'
    cache.delete(cache_key)
