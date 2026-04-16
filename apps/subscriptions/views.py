import logging
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.cache import cache

from api_response.helpers import success, fail, created
from payments.constants import Currency, PaymentPurpose
from .models import Plan, Subscription
from .serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    SubscribeSerializer,
)
from .services import SubscriptionService
from .api_schema import (
    plan_list_schema,
    subscribe_schema,
    my_subscription_schema,
    cancel_subscription_schema,
)
from .constants import (
    PLANS_LIST_CACHE_KEY,
    PLANS_LIST_CACHE_TTL,
    PaymentMethod,
)

logger = logging.getLogger(__name__)


@plan_list_schema
class PlanListView(APIView):
    """
    GET  /api/subscriptions/plans/       — list active plans (cached 30 min)
    GET supports ?currency=USD to return prices converted to USD.
    USD conversion uses the cached exchange rate — never a live API call.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        currency = request.query_params.get('currency', Currency.NGN).upper()

        # Cache key includes currency so NGN and USD lists are cached separately
        cache_key = f'{PLANS_LIST_CACHE_KEY}_{currency}'
        cached = cache.get(cache_key)

        if cached:
            return success(data=cached, message='Plans retrieved.')

        plans = Plan.objects.filter(is_active=True)
        serializer = PlanSerializer(plans, many=True)
        data = serializer.data

        # If USD requested, convert prices using cached exchange rate
        if currency == Currency.USD:
            data = self._convert_to_usd(data)

        cache.set(cache_key, data, timeout=PLANS_LIST_CACHE_TTL)
        return success(data=data, message='Plans retrieved.')

    @staticmethod
    def _convert_to_usd(plans_data):
        """
        Convert NGN prices to USD using cached exchange rate.
        Returns the same data structure with additional USD price fields.
        """
        try:
            from rates.services import ExchangeRateService
            rate = ExchangeRateService.get_ngn_to_usd_rate()
            for plan in plans_data:
                plan['monthly_price_usd'] = round(float(plan['monthly_price_ngn']) * rate, 2)
                plan['yearly_price_usd'] = round(float(plan['yearly_price_ngn']) * rate, 2)
        except Exception:
            import traceback
            logger.error(f'Failed to convert prices to USD: {traceback.format_exc()}')
        return plans_data


@subscribe_schema
class SubscribeView(APIView):
    """
    POST /api/subscriptions/

    Two payment flows:
        wallet  → deduct from wallet, activate immediately
        direct  → initiate Paystack/Stripe payment, activate on webhook
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = SubscribeSerializer(data=request.data)
        if not serializer.is_valid():
            return fail(message='Validation failed.', error=serializer.errors)

        plan_id = serializer.validated_data['plan_id']
        billing_cycle = serializer.validated_data['billing_cycle']
        payment_method = serializer.validated_data['payment_method']

        try:
            plan = Plan.objects.get(id=plan_id, is_active=True)
        except Plan.DoesNotExist:
            return fail(
                message='Plan not found or inactive.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if payment_method == PaymentMethod.WALLET:
            return self._handle_wallet_payment(request.user, plan, billing_cycle)

        return self._handle_direct_payment(request, plan, serializer.validated_data)

    def _handle_wallet_payment(self, user, plan, billing_cycle):
        # Pre-validate renewal eligibility before deducting from wallet
        can_renew, error_message = SubscriptionService.can_renew(
            user=user,
            plan_id=str(plan.id)
        )
        if not can_renew:
            return fail(
                message=error_message,
                error={'detail': error_message},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            subscription = SubscriptionService.subscribe_via_wallet(user, plan, billing_cycle)

            # Queue notification after successful wallet subscription
            from django.db import transaction
            from notifications.services import NotificationService
            transaction.on_commit(
                lambda: NotificationService.send_subscription_activated(user, plan)
            )

            return created(
                data=SubscriptionSerializer(subscription).data,
                message='Subscription activated successfully.',
            )
        except ValueError as exc:
            return fail(
                message=str(exc),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    def _handle_direct_payment(self, request, plan, validated_data):
        """
        Initiates a payment for a direct subscription.
        The subscription is NOT activated here — it's activated by the
        webhook handler when the payment succeeds.
        """
        # Pre-validate renewal eligibility before initiating payment
        can_renew, error_message = SubscriptionService.can_renew(
            user=request.user,
            plan_id=str(plan.id)
        )
        if not can_renew:
            return fail(
                message=error_message,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        idempotency_key = request.headers.get('X-Idempotency-Key')
        if not idempotency_key:
            return fail(
                message='X-Idempotency-Key header is required for direct payments.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        from payments.services.processor import PaymentProcessor, ConflictError
        from payments.constants import PaymentPurpose

        billing_cycle = validated_data['billing_cycle']
        amount = plan.monthly_price_ngn if billing_cycle == 'monthly' else plan.yearly_price_ngn
        request_params = {
            'amount': str(amount),
            'provider': validated_data['provider'],
            'purpose': PaymentPurpose.SUBSCRIPTION,
            'plan_id': str(plan.id),
            'billing_cycle': billing_cycle,
        }

        processor = PaymentProcessor(
            user=request.user,
            idempotency_key_value=idempotency_key,
            request_path=request.path,
            request_params=request_params,
        )

        try:
            response_body, response_code = processor.execute()
            return success(
                data=response_body,
                message='Payment initiated. Subscription will activate on payment confirmation.',
            )
        except ConflictError as exc:
            return fail(message=str(exc), status_code=status.HTTP_409_CONFLICT)


@my_subscription_schema
class MySubscriptionView(APIView):
    """GET /api/subscriptions/me/"""
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        subscription = SubscriptionService.get_active_subscription(request.user)
        if not subscription:
            return success(data=None, message='No active subscription.')
        return success(
            data=SubscriptionSerializer(subscription).data,
            message='Subscription retrieved.',
        )


@cancel_subscription_schema
class CancelSubscriptionView(APIView):
    """POST /api/subscriptions/cancel/"""
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            subscription = SubscriptionService.cancel(request.user)
            return success(
                data=SubscriptionSerializer(subscription).data,
                message='Subscription cancelled successfully.',
            )
        except ValueError as exc:
            return fail(message=str(exc), status_code=status.HTTP_400_BAD_REQUEST)