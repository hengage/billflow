from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache
from api_response.helpers import success, fail
from .serializers import WalletSerializer, WalletTransactionSerializer, TopUpSerializer
from .service import WalletService
from .constants import WALLET_BALANCE_CACHE_KEY_PREFIX


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


class WalletTopUpView(APIView):
    """
    POST /api/wallet/topup/ — initiates a wallet top-up.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = TopUpSerializer(data=request.data)

        if serializer.is_valid():
            amount = serializer.validated_data['amount']
            provider = serializer.validated_data['provider']

            # Payment initiation is handled by the payments app
            # We import here to avoid circular imports
            if provider == 'paystack':
                from payments.services import PaystackService
                result = PaystackService.initiate_payment(
                    user=request.user,
                    amount=amount,
                    purpose='wallet_topup',
                )
            else:
                from payments.services import StripeService
                result = StripeService.initiate_payment(
                    user=request.user,
                    amount=amount,
                    purpose='wallet_topup',
                )

            return success(
                data=result,
                message=f'Top-up initiated via {provider}. Complete payment to credit wallet.'
            )

        return fail(message='Validation failed.', error=serializer.errors)


class WalletTransactionListView(APIView):
    """
    GET /api/wallet/transactions/ — lists wallet transaction history.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        transactions = WalletService.get_transactions(request.user)
        serializer = WalletTransactionSerializer(transactions, many=True)
        return success(data=serializer.data, message='Transactions retrieved.')