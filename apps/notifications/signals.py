from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserNotificationPreferences

User = get_user_model()


@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    """
    Automatically create a UserNotificationPreferences record whenever
    a new User is created.
    """
    if created:
        UserNotificationPreferences.objects.create(user=instance)
