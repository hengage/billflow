from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from api_response.handlers import handler400, handler403, handler404, handler500


handler400 = handler400
handler403 = handler403
handler404 = handler404
handler500 = handler500

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path('accounts/', include('allauth.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/wallets/', include('wallets.urls')),

    # Schema endpoint — the raw OpenAPI JSON, used by Swagger UI and ReDoc
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Swagger UI — interactive documentation
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # ReDoc — cleaner read-only documentation
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
