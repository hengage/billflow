from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (OpenApiExample, OpenApiResponse,
                                   extend_schema)

from .serializers import LoginSerializer, RegisterSerializer

register_schema = extend_schema(
    summary='Register a new user',
    description='Creates a new customer account. Returns the user profile on success.',
    request=RegisterSerializer,
    responses={
        201: OpenApiResponse(description='Account created successfully.'),
        400: OpenApiResponse(description='Validation error.'),
    },
    tags=['Authentication'],
)

login_schema = extend_schema(
    summary='Login',
    description='Authenticates a user and returns JWT access and refresh tokens.',
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(description='Returns access token, refresh token, and user profile.'),
        400: OpenApiResponse(description='Invalid credentials.'),
    },
    tags=['Authentication'],
)

logout_schema = extend_schema(
    summary='Logout',
    description='Blacklists the refresh token. Access token expires naturally after 15 minutes.',
    responses={
        200: OpenApiResponse(description='Logged out successfully.'),
        400: OpenApiResponse(description='Refresh token missing or invalid.'),
    },
    tags=['Authentication'],
)

token_refresh_schema = extend_schema(
    summary='Refresh access token',
    description='Takes a valid refresh token and returns a new access token.',
    tags=['Authentication'],
)

profile_schema = extend_schema(
    summary='Get or update current user profile',
    description='GET returns the authenticated user profile. PATCH updates first_name, last_name, or notification preferences.',
    responses={
        200: OpenApiResponse(description='User profile.'),
    },
    tags=['Authentication'],
)

google_login_schema = extend_schema(
    summary='Google OAuth2 login',
    description=(
        'Accepts a Google access token obtained from the Google OAuth2 flow. '
        'Returns JWT access and refresh tokens on success. '
        'If the email does not exist, a new user account is created automatically.'
    ),
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'access_token': {
                    'type': 'string',
                    'description': 'Google OAuth2 access token (ya29.a0...)',
                }
            },
            'required': ['access_token'],
        }
    },
    responses={
        200: OpenApiTypes.OBJECT,
    },
    examples=[
        OpenApiExample(
            name='Google login request',
            value={'access_token': 'ya29.a0AfH6...'},
            request_only=True,
        ),
    ],
    tags=['Authentication'],
)

password_reset_schema = extend_schema(
    summary='Request password reset',
    description='Sends a password reset email to the provided address if it exists in the system.',
    tags=['Authentication'],
)

password_reset_confirm_schema = extend_schema(
    summary='Confirm password reset',
    description='Validates the reset token and sets the new password.',
    tags=['Authentication'],
)