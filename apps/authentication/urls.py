from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, LoginView, LogoutView, UserProfileView, GoogleLogin

urlpatterns = [
    path('register', RegisterView.as_view(), name='auth-register'),
    path('login', LoginView.as_view(), name='auth-login'),
    path('logout', LogoutView.as_view(), name='auth-logout'),
    path('token/refresh', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('me', UserProfileView.as_view(), name='auth-me'),
    path('google', GoogleLogin.as_view(), name='google-login'),
]