from django.contrib import admin
from .models import Notification, UserNotificationPreferences


@admin.register(UserNotificationPreferences)
class UserNotificationPreferencesAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'payments_email', 'payments_push',
        'subscriptions_email', 'subscriptions_push',
        'wallet_email', 'wallet_push',
    )
    search_fields = ('user__email',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'channel', 'sent_at', 'read')
    list_filter = ('type', 'channel', 'read')
    search_fields = ('user__email',)
    ordering = ('-sent_at',)