from django.urls import path
from .views import NotificationPreferencesView, PushNotificationListView

urlpatterns = [
    path('push', PushNotificationListView.as_view(), name='push-notification-list'),
    path('preferences', NotificationPreferencesView.as_view(), name='notification-preferences'),
]
