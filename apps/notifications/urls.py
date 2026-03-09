from django.urls import path
from .views import NotificationPreferencesView, NotificationListView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('preferences', NotificationPreferencesView.as_view(), name='notification-preferences'),
]
