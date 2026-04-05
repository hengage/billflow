from rest_framework import serializers
from .models import Wallet, WalletTransaction
from utils.messages import WALLET_MESSAGES
from payments.constants import (
    Currency,
    PaymentProvider,
    PROVIDER_CURRENCY_MAP,
    PROVIDER_MAX_AMOUNT_MAP,
)


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
    )
    provider = serializers.ChoiceField(choices=PaymentProvider.choices)

    def validate(self, attrs):
        provider = attrs.get('provider')
        amount = attrs.get('amount')
        
        
        currency = PROVIDER_CURRENCY_MAP.get(provider, Currency.NGN)
        max_amount = PROVIDER_MAX_AMOUNT_MAP.get(provider, 1000000)
        
        if amount and amount > max_amount:
            raise serializers.ValidationError(
                {'amount': f'Amount cannot exceed {max_amount:,.0f} {currency}.'}
            )
        return attrs