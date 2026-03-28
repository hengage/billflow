from drf_spectacular.utils import extend_schema
from drf_spectacular.openapi import OpenApiResponse
from .serializers import NotificationPreferencesSerializer, NotificationSerializer


notification_preferences_schema = extend_schema(
    summary='Get or update notification preferences',
    request=NotificationPreferencesSerializer,
    responses={
        200: OpenApiResponse(
            response=NotificationPreferencesSerializer,
            description='Notification preferences retrieved.'),
        400: OpenApiResponse(description='Validation failed.'),
    },
    tags=['Notifications'],
)

push_notification_list_schema = extend_schema(
    summary='List Push notifications',
    description='Returns a paginated list of push notifications for the authenticated user.',
    request=None,
    responses={
        200: OpenApiResponse(response=NotificationSerializer(many=True), description='Push notifications retrieved.'),
    },
    tags=['Notifications'],
)

mark_notification_read_schema = extend_schema(
    summary='Mark notification as read',
    description='Marks a specific notification as read for the authenticated user.',
    responses={
        200: OpenApiResponse(description='Notification marked as read.'),
        404: OpenApiResponse(description='Notification not found.'),
    },
    tags=['Notifications'],
)

mark_all_notifications_read_schema = extend_schema(
    summary='Mark all notifications as read',
    description='Marks all unread notifications as read for the authenticated user.',
    responses={
        200: OpenApiResponse(description='All notifications marked as read.'),
    },
    tags=['Notifications'],
)
