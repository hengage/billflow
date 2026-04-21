from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiResponse
from api_response.envelope_serializer import create_success_envelope
from .serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    SubscribeSerializer,
    SwitchPlanSerializer,
)


plan_list_schema = extend_schema(
    summary='List active plans',
    description=(
        'Returns all active subscription plans. '
        'Supports currency conversion to USD via query parameter. '
        'Results are cached for 30 minutes.'
    ),
    parameters=[
        OpenApiParameter(
            name='currency',
            location=OpenApiParameter.QUERY,
            required=False,
            type=str,
            description='Currency for price display. Options: NGN (default), USD',
            enum=['NGN', 'USD'],
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=create_success_envelope(PlanSerializer, many=True),
            description='List of active plans retrieved.',
        ),
        401: OpenApiResponse(description='Authentication required.'),
    },
    tags=['Subscriptions'],
)


subscribe_schema = extend_schema(
    summary='Subscribe to a plan',
    description=(
        'Creates a subscription to a plan. '
        'Two payment flows: '
        '1) wallet - deducts from wallet balance immediately. '
        '2) direct - initiates Paystack/Stripe payment, activates on webhook confirmation. '
        'Requires X-Idempotency-Key header for direct payments.'
    ),
    request=SubscribeSerializer,
    parameters=[
        OpenApiParameter(
            name='X-Idempotency-Key',
            type=str,
            location=OpenApiParameter.HEADER,
            description='Unique key for idempotent direct payment requests. Required when payment_method=direct.',
            required=False,
        ),
    ],
    responses={
        201: OpenApiResponse(
            response=create_success_envelope(SubscriptionSerializer),
            description='Subscription activated (wallet) or payment initiated (direct).',
        ),
        400: OpenApiResponse(description='Validation failed.'),
        401: OpenApiResponse(description='Authentication required.'),
        404: OpenApiResponse(description='Plan not found or inactive.'),
        409: OpenApiResponse(description='Conflict - request already being processed.'),
    },
    tags=['Subscriptions'],
)


renew_schema = extend_schema(
    summary='Renew subscription',
    description=(
        'Extends an existing subscription. Requires active subscription within '
        '7 days of expiry (renewal eligibility gate). '
        'Two payment flows: '
        '1) wallet - deducts from wallet balance immediately. '
        '2) direct - initiates Paystack/Stripe payment, renews on webhook confirmation. '
        'Requires X-Idempotency-Key header for direct payments.'
    ),
    request=SubscribeSerializer,
    parameters=[
        OpenApiParameter(
            name='X-Idempotency-Key',
            type=str,
            location=OpenApiParameter.HEADER,
            description='Unique key for idempotent direct payment requests. Required when payment_method=direct.',
            required=False,
        ),
    ],
    responses={
        201: OpenApiResponse(
            response=create_success_envelope(SubscriptionSerializer),
            description='Subscription renewed (wallet) or payment initiated (direct).',
        ),
        400: OpenApiResponse(description='Validation failed or renewal not eligible.'),
        401: OpenApiResponse(description='Authentication required.'),
        404: OpenApiResponse(description='No active subscription to renew.'),
        409: OpenApiResponse(description='Conflict - request already being processed.'),
    },
    tags=['Subscriptions'],
)


my_subscription_schema = extend_schema(
    summary='Get my active subscription',
    description='Returns the authenticated user\'s active subscription if any.',
    responses={
        200: OpenApiResponse(
            response=create_success_envelope(SubscriptionSerializer),
            description='Active subscription retrieved or null if none.',
        ),
        401: OpenApiResponse(description='Authentication required.'),
    },
    tags=['Subscriptions'],
)


cancel_subscription_schema = extend_schema(
    summary='Cancel subscription',
    description='Cancels the authenticated user\'s active subscription.',
    responses={
        200: OpenApiResponse(
            response=create_success_envelope(SubscriptionSerializer),
            description='Subscription cancelled successfully.',
        ),
        400: OpenApiResponse(description='No active subscription to cancel.'),
        401: OpenApiResponse(description='Authentication required.'),
    },
    tags=['Subscriptions'],
)


switch_plan_schema = extend_schema(
    summary='Switch to a different plan',
    description=(
        'Switches to a different plan immediately. '
        'Cancels current subscription and creates new one with full billing cycle. '
        'Two payment flows: '
        '1) wallet - deducts from wallet balance immediately. '
        '2) direct - initiates Paystack/Stripe payment, switches on webhook confirmation. '
        'Requires X-Idempotency-Key header for direct payments.'
    ),
    request=SwitchPlanSerializer,
    parameters=[
        OpenApiParameter(
            name='X-Idempotency-Key',
            type=str,
            location=OpenApiParameter.HEADER,
            description='Unique key for idempotent direct payment requests. Required when payment_method=direct.',
            required=False,
        ),
    ],
    responses={
        201: OpenApiResponse(
            response=create_success_envelope(SubscriptionSerializer),
            description='Plan switched (wallet) or payment initiated (direct).',
        ),
        400: OpenApiResponse(description='Validation failed or cannot switch to same plan.'),
        401: OpenApiResponse(description='Authentication required.'),
        404: OpenApiResponse(description='Plan not found or inactive.'),
        409: OpenApiResponse(description='Conflict - request already being processed.'),
    },
    tags=['Subscriptions'],
)
