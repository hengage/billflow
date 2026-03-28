from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import Wallet

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
