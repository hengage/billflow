from rest_framework import serializers
from .models import Payment
from .constants import PaymentProvider, PaymentPurpose, Currency


class InitiatePaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=100)
    provider = serializers.ChoiceField(choices=PaymentProvider.choices)
    purpose = serializers.ChoiceField(choices=PaymentPurpose.choices)
    # plan_id is only required when purpose is subscription
    plan_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if attrs.get('purpose') == PaymentPurpose.SUBSCRIPTION and not attrs.get('plan_id'):
            raise serializers.ValidationError(
                {'plan_id': 'plan_id is required for subscription payments.'}
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
    reference = serializers.UUIDField()
