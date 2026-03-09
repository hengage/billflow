from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from api_response.helpers import success, fail
from .models import Notification
from .serializers import NotificationPreferencesSerializer, NotificationSerializer


class NotificationPreferencesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        # Return the user's current preferences
        # If they've never set preferences, notification_preferences is {}
        return success(
            data=request.user.notification_preferences,
            message='Notification preferences retrieved.'
        )

    def patch(self, request):
        serializer = NotificationPreferencesSerializer(
            instance=request.user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return success(
                data=request.user.notification_preferences,
                message='Notification preferences updated.'
            )

        return fail(
            message='Validation failed.',
            error=serializer.errors
        )


class NotificationListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        serializer = NotificationSerializer(notifications, many=True)
        return success(
            data=serializer.data,
            message='Notifications retrieved.'
        )
