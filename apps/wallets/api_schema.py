from drf_spectacular.utils import extend_schema
from drf_spectacular.openapi import OpenApiResponse
from .serializers import WalletSerializer, WalletTransactionSerializer, TopUpSerializer


wallet_balance_schema = extend_schema(
    summary='Get wallet balance',
    description='Returns the current wallet balance for the authenticated user. Balance is cached for 2 minutes.',
    request=None,
    responses={
        200: OpenApiResponse(response=WalletSerializer, description='Wallet balance retrieved.'),
    },
    tags=['Wallet'],
)

wallet_topup_schema = extend_schema(
    summary='Initiate wallet top-up',
    description='Initiates a wallet top-up via Paystack or Stripe. Returns payment details to complete the transaction.',
    request=TopUpSerializer,
    responses={
        200: OpenApiResponse(description='Top-up initiated. Complete payment to credit wallet.'),
        400: OpenApiResponse(description='Validation failed.'),
    },
    tags=['Wallet'],
)

wallet_transactions_schema = extend_schema(
    summary='List wallet transactions',
    description='Returns a list of all wallet transactions (top-ups and deductions) for the authenticated user.',
    request=None,
    responses={
        200: OpenApiResponse(response=WalletTransactionSerializer(many=True), description='Transactions retrieved.'),
    },
    tags=['Wallet'],
)
