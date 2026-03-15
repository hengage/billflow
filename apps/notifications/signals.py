from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import UserNotificationPreferences

User = get_user_model()


@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    if created:
        # on_commit is used here to defer creation until the User transaction is fully
        # committed — prevents creating preferences for a User that might
        # still be rolled back
        transaction.on_commit(
            lambda: UserNotificationPreferences.objects.get_or_create(user=instance)
        )