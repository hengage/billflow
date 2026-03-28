from rest_framework import serializers
from .models import Wallet, WalletTransaction


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
    )
    provider = serializers.ChoiceField(choices=['paystack', 'stripe'])

    def validate_amount(self, value):
        # Ensure amount has at most 2 decimal places
        # DecimalField handles this but explicit validation gives a cleaner error
        if round(value, 2) != value:
            raise serializers.ValidationError(
                'Amount must have at most 2 decimal places.'
            )
        return value