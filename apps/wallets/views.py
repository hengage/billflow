from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.core.cache import cache
from api_response.helpers import success, fail
from api_response.exceptions import ConflictError
import logging

logger = logging.getLogger(__name__)

from .serializers import WalletSerializer, WalletTransactionSerializer, TopUpSerializer
from .service import WalletService
from .constants import WALLET_BALANCE_CACHE_KEY_PREFIX
from .api_schema import wallet_balance_schema, wallet_topup_schema, wallet_transactions_schema


@wallet_balance_schema
class WalletView(APIView):
    """
    GET /api/wallet/ — returns current wallet balance.
    Balance is cached for 2 minutes for display purposes.
    Cache is invalidated by post_save signal on Wallet model.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        cache_key = f'{WALLET_BALANCE_CACHE_KEY_PREFIX}_{request.user.id}'
        cached_data = cache.get(cache_key)

        if cached_data:
            return success(data=cached_data, message='Wallet balance retrieved.')

        wallet = WalletService.get_balance(request.user)
        data = WalletSerializer(wallet).data

        # Cache for 2 minutes — display only
        cache.set(cache_key, data, timeout=120)

        return success(data=data, message='Wallet balance retrieved.')


@wallet_topup_schema
class WalletTopUpView(APIView):
    """
    POST /api/wallet/topup/ — initiates a wallet top-up.

    Delegates entirely to PaymentProcessor — same idempotency,
    atomic phases, and provider abstraction as direct payments.
    The only difference is purpose is always wallet_topup.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = TopUpSerializer(data=request.data)
        if not serializer.is_valid():
            return fail(message='Validation failed.', error=serializer.errors)

        idempotency_key = request.headers.get('X-Idempotency-Key')
        if not idempotency_key:
            return fail(
                message='X-Idempotency-Key header is required.',
                error={'X-Idempotency-Key': 'This header is required for top-up requests.'},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        from payments.services.processor import PaymentProcessor
        from payments.constants import PaymentPurpose
        from utils.messages import PAYMENT_MESSAGES

        request_params = {
            'amount': str(serializer.validated_data['amount']),
            'provider': serializer.validated_data['provider'],
            'purpose': PaymentPurpose.WALLET_TOPUP,
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
                message='Top-up initiated. Complete payment to credit your wallet.',
            )
        except ConflictError as exc:
            return fail(
                message=str(exc),
                error={'detail': str(exc)},
                status_code=status.HTTP_409_CONFLICT,
            )
        except ValidationError as exc:
            return fail(
                message=str(exc),
                error={'detail': str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception('Wallet top-up failed')
            return fail(
                message='Payment service temporarily unavailable.',
                error={'detail': str(exc)},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


@wallet_transactions_schema
class WalletTransactionListView(APIView):
    """
    GET /api/wallet/transactions/ — lists wallet transaction history.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        transactions = WalletService.get_transactions(request.user)
        serializer = WalletTransactionSerializer(transactions, many=True)
        return success(data=serializer.data, message='Transactions retrieved.')