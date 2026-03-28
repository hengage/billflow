from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .models import Wallet
from .constants import WALLET_BALANCE_CACHE_KEY_PREFIX

User = get_user_model()


@receiver(post_save, sender=User)
def create_wallet(sender, instance, created, **kwargs):
    """
    Automatically create a Wallet for every new User.
    on_commit ensures the wallet is only created after the User
    transaction is fully committed — never for a rolled-back User.
    """
    if created:
        transaction.on_commit(
            lambda: Wallet.objects.get_or_create(user=instance)
        )


@receiver(post_save, sender=Wallet)
def invalidate_wallet_cache(sender, instance, **kwargs):
    """
    Invalidate the wallet balance cache whenever the wallet is saved.
    This ensures the cached balance never shows stale data after a
    top-up or deduction updates the actual balance.
    """
    cache_key = f'{WALLET_BALANCE_CACHE_KEY_PREFIX}_{instance.user_id}'
    cache.delete(cache_key)
