from rest_framework import serializers
from .models import Notification, UserNotificationPreferences
from .constants import NotificationGroup, NOTIFICATION_GROUP_DESCRIPTIONS


class NotificationGroupPreferenceSerializer(serializers.Serializer):
    """Validates a single group's email and push toggles."""
    email = serializers.BooleanField()
    push = serializers.BooleanField()


class NotificationPreferencesSerializer(serializers.Serializer):
    """
    Validates the incoming PATCH body for notification preferences.
    All groups are optional — a PATCH with just {"payments": {...}} is valid
    and leaves subscriptions and wallet preferences untouched.
    """
    payments = NotificationGroupPreferenceSerializer(required=False)
    subscriptions = NotificationGroupPreferenceSerializer(required=False)
    wallet = NotificationGroupPreferenceSerializer(required=False)

    def update(self, instance, validated_data):
        """
        Updates only the specific columns that were sent in the request.
        update_fields ensures Django issues a targeted UPDATE statement rather
        than writing every column on the row.
        """
        fields_to_update = []

        if 'payments' in validated_data:
            instance.payments_email = validated_data['payments']['email']
            instance.payments_push = validated_data['payments']['push']
            fields_to_update.extend(['payments_email', 'payments_push'])

        if 'subscriptions' in validated_data:
            instance.subscriptions_email = validated_data['subscriptions']['email']
            instance.subscriptions_push = validated_data['subscriptions']['push']
            fields_to_update.extend(['subscriptions_email', 'subscriptions_push'])

        if 'wallet' in validated_data:
            instance.wallet_email = validated_data['wallet']['email']
            instance.wallet_push = validated_data['wallet']['push']
            fields_to_update.extend(['wallet_email', 'wallet_push'])

        if fields_to_update:
            instance.save(update_fields=fields_to_update)

        return instance

    @staticmethod
    def to_representation_with_descriptions(preferences_obj):
        """
        Builds the API response structure by merging database values with
        static descriptions from constants. Descriptions are never stored
        in the database — they are injected at read time.
        """
        return {
            NotificationGroup.PAYMENTS: {
                'description': NOTIFICATION_GROUP_DESCRIPTIONS[NotificationGroup.PAYMENTS],
                'email': preferences_obj.payments_email,
                'push': preferences_obj.payments_push,
            },
            NotificationGroup.SUBSCRIPTIONS: {
                'description': NOTIFICATION_GROUP_DESCRIPTIONS[NotificationGroup.SUBSCRIPTIONS],
                'email': preferences_obj.subscriptions_email,
                'push': preferences_obj.subscriptions_push,
            },
            NotificationGroup.WALLET: {
                'description': NOTIFICATION_GROUP_DESCRIPTIONS[NotificationGroup.WALLET],
                'email': preferences_obj.wallet_email,
                'push': preferences_obj.wallet_push,
            },
        }


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'type', 'channel', 'message', 'sent_at', 'read')
        read_only_fields = ('id', 'type', 'channel', 'message', 'sent_at')