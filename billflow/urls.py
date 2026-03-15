from django.contrib import admin
from django.urls import path, include
from api_response import handlers as error_handlers


handler400 = error_handlers.handler400
handler403 = error_handlers.handler403
handler404 = error_handlers.handler404
handler500 = error_handlers.handler500

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path('api/notifications/', include('notifications.urls')),
]
