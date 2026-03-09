from rest_framework import serializers
from .constants import NotificationGroup
from .models import Notification


class NotificationGroupPreferenceSerializer(serializers.Serializer):
    """
    Validates a single group's preference object.
    e.g. {"email": true, "push": false}
    Used as a nested serializer inside NotificationPreferencesSerializer.
    """
    email = serializers.BooleanField()
    push = serializers.BooleanField()


class NotificationPreferencesSerializer(serializers.Serializer):
    """
    Validates the full preferences payload.
    Each group is a nested NotificationGroupPreferenceSerializer.
    All fields are optional.
    """
    payments = NotificationGroupPreferenceSerializer(required=False)
    subscriptions = NotificationGroupPreferenceSerializer(required=False)
    wallet = NotificationGroupPreferenceSerializer(required=False)

    def update(self, instance, validated_data):
        # instance here is the User object
        # Merge the incoming preferences with the existing ones
        # rather than replacing the whole structure
        current_prefs = instance.notification_preferences or {}
        current_prefs.update(validated_data)
        instance.notification_preferences = current_prefs
        instance.save()
        return instance


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'type', 'channel', 'message', 'sent_at', 'read')
        read_only_fields = ('id', 'type', 'channel', 'message', 'sent_at')
