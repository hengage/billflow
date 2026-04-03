from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiResponse
from .serializers import (
    InitiatePaymentSerializer,
    PaymentHistorySerializer,
    PaymentInitiateResponseSerializer,
)


payment_initiate_schema = extend_schema(
    summary='Initiate a payment',
    description=(
        'Initiates a payment via Paystack or Stripe. '
        'Returns a checkout URL for the user to complete payment. '
        'Requires X-Idempotency-Key header for safe retries.'
    ),
    parameters=[
        OpenApiParameter(
            name='X-Idempotency-Key',
            location=OpenApiParameter.HEADER,
            required=True,
            type=str,
            description='UUID for idempotent request handling.',
        ),
    ],
    request=InitiatePaymentSerializer,
    responses={
        200: OpenApiResponse(
            response=PaymentInitiateResponseSerializer,
            description='Payment initiated successfully.',
        ),
        400: OpenApiResponse(description='Validation failed or missing idempotency key.'),
        409: OpenApiResponse(description='Request conflict — already being processed.'),
        503: OpenApiResponse(description='Payment system at capacity.'),
    },
    tags=['Payments'],
)

payment_history_schema = extend_schema(
    summary='List payment history',
    description='Returns all payment attempts for the authenticated user.',
    request=None,
    responses={
        200: OpenApiResponse(
            response=PaymentHistorySerializer(many=True),
            description='Payment history retrieved.',
        ),
    },
    tags=['Payments'],
)

paystack_verify_schema = extend_schema(
    summary='Verify Paystack transaction',
    description='Manually verify a transaction status directly with Paystack.',
    request=None,
    responses={
        200: OpenApiResponse(description='Transaction verified.'),
        503: OpenApiResponse(description='Paystack service unavailable.'),
    },
    tags=['Payments'],
)

paystack_webhook_schema = extend_schema(
    summary='Paystack webhook endpoint',
    description=(
        'Receives webhook events from Paystack. '
        'Signature verification required. Returns 200 immediately, processes asynchronously.'
    ),
    request=None,
    responses={
        200: OpenApiResponse(description='Webhook received.'),
        400: OpenApiResponse(description='Invalid signature.'),
    },
    tags=['Payments'],
)

stripe_webhook_schema = extend_schema(
    summary='Stripe webhook endpoint',
    description=(
        'Receives webhook events from Stripe. '
        'Signature verification required. Returns 200 immediately, processes asynchronously.'
    ),
    request=None,
    responses={
        200: OpenApiResponse(description='Webhook received.'),
        400: OpenApiResponse(description='Invalid signature.'),
    },
    tags=['Payments'],
)
