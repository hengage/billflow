from rest_framework import serializers
from .models import Wallet, WalletTransaction
from utils.messages import WALLET_MESSAGES


class WalletSerializer(serializers.ModelSerializer):
    """Read-only serializer for wallet balance display."""
    class Meta:
        model = Wallet
        fields = ('id', 'balance', 'currency', 'updated_at')
        read_only_fields = ('id', 'balance', 'currency', 'updated_at')


class WalletTransactionSerializer(serializers.ModelSerializer):
    """Read-only serializer for transaction history."""
    class Meta:
        model = WalletTransaction
        fields = ('id', 'amount', 'type', 'reference', 'created_at')
        read_only_fields = fields


class TopUpSerializer(serializers.Serializer):
    """
    Validates top-up initiation request.
    """
    amount = serializers.DecimalField(
        max_digits=9,
        decimal_places=2,
        min_value=100,
        max_value=1000000,
        error_messages={
            'max_value': WALLET_MESSAGES['TOPUP_MAX_LIMIT'],
            'max_digits': WALLET_MESSAGES['TOPUP_MAX_LIMIT'],
            'min_value': WALLET_MESSAGES['TOPUP_MIN_LIMIT'],
        }
    )
    provider = serializers.ChoiceField(choices=['paystack', 'stripe'])