# apps/authentication/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView

from .serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer
from api_response.helpers import created, fail, success
from .api_schema import (
    register_schema,
    login_schema,
    logout_schema,
    profile_schema,
    google_login_schema,
)

@google_login_schema
class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = 'http://localhost:3000/auth/google/callback'
    client_class = OAuth2Client

@register_schema
class RegisterView(APIView):
    # Override the global DEFAULT_PERMISSION_CLASSES which requires authentication
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        print(serializer.is_valid())
        print(serializer.errors)

        if serializer.is_valid():
            user = serializer.save()
            return created(
                data={'user': UserProfileSerializer(user).data},
                message='Account created successfully.'
            )

        return fail(
            message='Validation failed',
            error=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )


@login_schema
class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={'request': request}
        )

        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)

            return success(
                data={
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'user': UserProfileSerializer(user).data,
                },
                message='Login successful'
            )

        return fail(
            message='Invalid credentials',
            error=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )


@logout_schema
class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        refresh_token = request.data.get('refresh')

        if not refresh_token:
            return fail(
                message='Refresh token is required.',
                error={'refresh': 'This field is required.'},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            # This adds to token to the OutstandingToken blacklist
            # Any future attempt to use it will be rejected by simplejwt
            token = RefreshToken(refresh_token)
            token.blacklist()
            return success(
                message='Logged out successfully.'
            )
        except TokenError:
            return fail(
                message='Invalid or expired token.',
                error={'token': 'Invalid or expired refresh token.'},
                status_code=status.HTTP_400_BAD_REQUEST
            )


@profile_schema
class UserProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return success(data=serializer.data)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return success(data=serializer.data, message='Profile updated successfully.')

        return fail(
            message='Validation failed',
            error=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )