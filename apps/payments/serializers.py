from rest_framework import serializers
from .models import Payment
from .constants import PaymentProvider, PaymentPurpose, Currency, PROVIDER_CURRENCY_MAP, PROVIDER_MAX_AMOUNT_MAP


class InitiatePaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=100,
    )
    provider = serializers.ChoiceField(choices=PaymentProvider.choices)
    purpose = serializers.ChoiceField(choices=PaymentPurpose.choices)
    # plan_id is only required when purpose is subscription
    plan_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        provider = attrs.get('provider')
        amount = attrs.get('amount')
        currency = PROVIDER_CURRENCY_MAP.get(provider, Currency.NGN)
        
        max_amount = PROVIDER_MAX_AMOUNT_MAP.get(provider, 1000000)
        
        if amount and amount > max_amount:
            raise serializers.ValidationError(
                {'amount': f'Amount cannot exceed {max_amount:,.0f} {currency}.'}
            )
        if attrs.get('purpose') == PaymentPurpose.SUBSCRIPTION and not attrs.get('plan_id'):
            raise serializers.ValidationError(
                {'plan_id': 'plan_id is required for subscription payments.'}
            )
        if attrs.get('purpose') == PaymentPurpose.WALLET_TOPUP and attrs.get('plan_id'):
            raise serializers.ValidationError(
                {'plan_id': 'plan_id should not be provided for wallet top-up payments.'}
            )
        return attrs


class PaymentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'id', 'amount', 'currency', 'provider', 'status',
            'purpose', 'reference', 'last_four', 'card_brand', 'created_at',
        )
        read_only_fields = fields


class PaymentInitiateResponseSerializer(serializers.Serializer):
    """Response data for successful payment initiation."""
    checkout_url = serializers.URLField()
    reference = serializers.CharField()
