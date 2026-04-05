import logging
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.cache import cache

from api_response.helpers import success, fail, created
from users.permissions import IsAdmin
from payments.constants import PaymentPurpose
from .models import Plan, Subscription
from .serializers import (
    PlanSerializer,
    PlanCreateSerializer,
    SubscriptionSerializer,
    SubscribeSerializer,
)
from .services import SubscriptionService
from .constants import (
    PLANS_LIST_CACHE_KEY,
    PLANS_LIST_CACHE_TTL,
    PaymentMethod,
)

logger = logging.getLogger(__name__)


class PlanListCreateView(APIView):
    """
    GET  /api/subscriptions/plans/       — list active plans (cached 30 min)
    POST /api/subscriptions/plans/       — create plan (admin only)

    GET supports ?currency=USD to return prices converted to USD.
    USD conversion uses the cached exchange rate — never a live API call.
    """

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        currency = request.query_params.get('currency', 'NGN').upper()

        # Cache key includes currency so NGN and USD lists are cached separately
        cache_key = f'{PLANS_LIST_CACHE_KEY}_{currency}'
        cached = cache.get(cache_key)

        if cached:
            return success(data=cached, message='Plans retrieved.')

        plans = Plan.objects.filter(is_active=True)
        serializer = PlanSerializer(plans, many=True)
        data = serializer.data

        # If USD requested, convert prices using cached exchange rate
        if currency == 'USD':
            data = self._convert_to_usd(data)

        cache.set(cache_key, data, timeout=PLANS_LIST_CACHE_TTL)
        return success(data=data, message='Plans retrieved.')

    def post(self, request):
        serializer = PlanCreateSerializer(data=request.data)
        if serializer.is_valid():
            plan = serializer.save()
            return created(
                data=PlanSerializer(plan).data,
                message='Plan created successfully.',
            )
        return fail(message='Validation failed.', error=serializer.errors)

    @staticmethod
    def _convert_to_usd(plans_data):
        """
        Converts plan prices to USD using the cached exchange rate.
        Falls back to stored price_usd if rate is unavailable.
        """
        try:
            from rates.services import ExchangeRateService
            rate = ExchangeRateService.get_ngn_to_usd_rate()
            for plan in plans_data:
                plan['price_usd'] = round(
                    float(plan['price_ngn']) * rate, 2
                )
        except Exception:
            # Rate service unavailable — serve stored price_usd as fallback
            logger.warning('Exchange rate unavailable — serving stored USD prices')
        return plans_data


class PlanDetailView(APIView):
    """
    GET    /api/subscriptions/plans/<id>/  — plan detail
    PATCH  /api/subscriptions/plans/<id>/  — update plan (admin only)
    DELETE /api/subscriptions/plans/<id>/  — delete plan (admin only)
    """

    def get_permissions(self):
        if self.request.method in ('PATCH', 'DELETE'):
            return [IsAdmin()]
        return [IsAuthenticated()]

    def _get_plan(self, pk):
        try:
            return Plan.objects.get(id=pk)
        except Plan.DoesNotExist:
            return None

    def get(self, request, pk):
        plan = self._get_plan(pk)
        if not plan:
            return fail(message='Plan not found.', status_code=status.HTTP_404_NOT_FOUND)
        return success(data=PlanSerializer(plan).data, message='Plan retrieved.')

    def patch(self, request, pk):
        plan = self._get_plan(pk)
        if not plan:
            return fail(message='Plan not found.', status_code=status.HTTP_404_NOT_FOUND)

        serializer = PlanCreateSerializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            plan = serializer.save()
            return success(
                data=PlanSerializer(plan).data,
                message='Plan updated successfully.',
            )
        return fail(message='Validation failed.', error=serializer.errors)

    def delete(self, request, pk):
        plan = self._get_plan(pk)
        if not plan:
            return fail(message='Plan not found.', status_code=status.HTTP_404_NOT_FOUND)

        # Soft delete — mark inactive rather than hard delete
        # Hard delete would fail if any Subscription references this plan (PROTECT)
        plan.is_active = False
        plan.save(update_fields=['is_active'])
        return success(message='Plan deactivated successfully.')


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
        payment_method = serializer.validated_data['payment_method']

        try:
            plan = Plan.objects.get(id=plan_id, is_active=True)
        except Plan.DoesNotExist:
            return fail(
                message='Plan not found or inactive.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if payment_method == PaymentMethod.WALLET:
            return self._handle_wallet_payment(request.user, plan)

        return self._handle_direct_payment(request, plan, serializer.validated_data)

    def _handle_wallet_payment(self, user, plan):
        try:
            subscription = SubscriptionService.subscribe_via_wallet(user, plan)

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
        idempotency_key = request.headers.get('X-Idempotency-Key')
        if not idempotency_key:
            return fail(
                message='X-Idempotency-Key header is required for direct payments.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        from payments.services.processor import PaymentProcessor, ConflictError
        from payments.constants import PaymentPurpose

        request_params = {
            'amount': str(plan.price_ngn),
            'provider': validated_data['provider'],
            'purpose': PaymentPurpose.SUBSCRIPTION,
            'plan_id': str(plan.id),
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


class AdminSubscriptionListView(APIView):
    """GET /api/subscriptions/ — admin only"""
    permission_classes = (IsAdmin,)

    def get(self, request):
        subscriptions = Subscription.objects.select_related(
            'user', 'plan'
        ).all()
        serializer = SubscriptionSerializer(subscriptions, many=True)
        return success(data=serializer.data, message='Subscriptions retrieved.')