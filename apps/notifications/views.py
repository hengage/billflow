from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from api_response.helpers import success, fail
from .models import Notification
from .serializers import (
    NotificationPreferencesSerializer,
    NotificationSerializer,
)


class NotificationPreferencesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        # Every user has a preferences record created automatically at registration
        # via Django signal — so .notification_preferences_obj will always exist
        preferences = request.user.notification_preferences_obj
        data = NotificationPreferencesSerializer.to_representation_with_descriptions(preferences)
        return success(data=data, message='Notification preferences retrieved.')

    def patch(self, request):
        preferences = request.user.notification_preferences_obj
        serializer = NotificationPreferencesSerializer(
            instance=preferences,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            updated = serializer.save()
            data = NotificationPreferencesSerializer.to_representation_with_descriptions(updated)
            return success(data=data, message='Notification preferences updated.')

        return fail(message='Validation failed.', error=serializer.errors)


class PushNotificationListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user, channel='push')
        serializer = NotificationSerializer(notifications, many=True)
        return success(data=serializer.data, message='Notifications retrieved.')