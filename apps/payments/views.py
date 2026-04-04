import logging
import stripe
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from api_response.helpers import fail, success
from api_response.exceptions import ConflictError
from payments.constants import PaymentProvider
from payments.models import Payment, WebhookLog
from payments.serializers import (
    InitiatePaymentSerializer,
    PaymentHistorySerializer,
)
from payments.services.processor import PaymentProcessor
from payments.services.providers.paystack import PaystackProvider
from payments.services.providers.stripe import StripeProvider
from payments.decorators import payment_capacity_limiter
from payments.tasks import process_webhook_event
from payments.api_schema import (
    payment_initiate_schema,
    payment_history_schema,
    paystack_verify_schema,
    paystack_webhook_schema,
    stripe_webhook_schema,
)
from utils.messages import PAYMENT_MESSAGES

logger = logging.getLogger(__name__)


@payment_initiate_schema
@method_decorator(payment_capacity_limiter, name='dispatch')
class InitiatePaymentView(APIView):
    """
    POST /api/payments/initiate/

    Validates the request, instantiates the PaymentProcessor, and delegates
    the entire payment initiation lifecycle to it.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        idempotency_key = request.headers.get('X-Idempotency-Key')
        if not idempotency_key:
            return fail(
                message='X-Idempotency-Key header is required.',
                error={'X-Idempotency-Key': 'This header is required for payment requests.'},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InitiatePaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return fail(message='Validation failed.', error=serializer.errors)

        request_params = {
            'amount': str(serializer.validated_data['amount']),
            'currency': serializer.validated_data.get('currency', 'NGN'),
            'provider': serializer.validated_data['provider'],
            'purpose': serializer.validated_data['purpose'],
            # Include plan_id in params for subscription payments so the
            # processor can pass it through to the webhook handler via metadata
            **({'plan_id': str(serializer.validated_data['plan_id'])}
               if 'plan_id' in serializer.validated_data else {}),
        }

        processor = PaymentProcessor(
            user=request.user,
            idempotency_key_value=idempotency_key,
            request_path=request.path,
            request_params=request_params,
        )

        try:
            response_body, response_code = processor.execute()
            if response_code != status.HTTP_200_OK:
                return fail(
                    message=PAYMENT_MESSAGES['FAILED'],
                    error=response_body,
                    status_code=response_code,
                )
            return success(
                data=response_body,
                message='Payment initiated successfully.',
            )

        except ConflictError as exc:
            return fail(
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )

        except ValidationError as exc:
            return fail(
                message=str(exc),
                error={'detail': str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:
            logger.exception('Payment initiation failed')
            return fail(
                message='Payment service temporarily unavailable.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


@paystack_webhook_schema
@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    """
    POST /api/payments/paystack/webhook/

    Receives webhook events from Paystack.
    The webhook handler follows a strict three-step protocol:
        1. Verify signature — reject anything that fails with 400
        2. Write to WebhookLog — before touching anything else
        3. Queue Celery task — return 200 immediately, process asynchronously
    """
    permission_classes = (AllowAny,)

    def post(self, request):
        signature = request.headers.get('X-Paystack-Signature', '')
        if not PaystackProvider.verify_signature(request.body, signature):
            logger.warning(
                f'Paystack webhook signature verification failed | '
                f'ip={request.META.get("REMOTE_ADDR")}'
            )
            return fail(
                message='Invalid webhook signature.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        payload = request.data
        event_type = payload.get('event', '')

        # This is our audit trail and replay mechanism. If processing fails,
        # the event is here to inspect and manually trigger again.
        webhook_log = WebhookLog.objects.create(
            provider=PaymentProvider.PAYSTACK,
            event_type=event_type,
            payload=payload,
        )

        transaction.on_commit(
            lambda: process_webhook_event.delay(
                webhook_log_id=str(webhook_log.id),
                provider=PaymentProvider.PAYSTACK,
            )
        )

        return success(message='Webhook received.')


@stripe_webhook_schema
@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """
    POST /api/payments/stripe/webhook/
    """
    permission_classes = (AllowAny,)

    def post(self, request):
        signature = request.headers.get('Stripe-Signature', '')

        try:
            event = StripeProvider.verify_signature(request.body, signature)
        except stripe.error.SignatureVerificationError:
            logger.warning(
                f'Stripe webhook signature verification failed | '
                f'ip={request.META.get("REMOTE_ADDR")}'
            )
            return fail(
                message='Invalid webhook signature.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        webhook_log = WebhookLog.objects.create(
            provider=PaymentProvider.STRIPE,
            event_type=event['type'],
            payload=dict(event),
        )

        transaction.on_commit(
            lambda: process_webhook_event.delay(
                webhook_log_id=str(webhook_log.id),
                provider=PaymentProvider.STRIPE,
            )
        )

        return success(message='Webhook received.')


@paystack_verify_schema
class PaystackVerifyView(APIView):
    """
    GET /api/payments/paystack/verify/<reference>/

    Allows clients to manually verify a transaction status directly
    with Paystack. Useful when a user completes payment but the webhook
    hasn't arrived yet — the client can poll this endpoint to check.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, reference):
        try:
            result = PaystackProvider.verify_transaction(reference)
            return success(data=result, message='Transaction verified.')
        except Exception as exc:
            return fail(
                message=str(exc),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


@payment_history_schema
class PaymentHistoryView(APIView):
    """
    GET /api/payments/history/

    Returns all payment attempts for the current user, including pending,
    successful, and failed ones. Filtered strictly to request.user —
    users can never see another user's payment history.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        payments = Payment.objects.filter(user=request.user)
        serializer = PaymentHistorySerializer(payments, many=True)
        return success(data=serializer.data, message='Payment history retrieved.')