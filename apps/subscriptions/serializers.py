from rest_framework import serializers
from .models import Plan, Subscription
from .constants import PaymentMethod


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            'id', 'name', 'description', 'monthly_price_ngn', 'yearly_price_ngn',
            'features', 'is_active', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class PlanCreateSerializer(serializers.ModelSerializer):
    """
    Used by admin for creating and updating plans.
    Separate from PlanSerializer to keep the read and write
    shapes explicit — the read serializer might add computed
    fields later (like USD price from live rates) that shouldn't
    be writable.
    """
    class Meta:
        model = Plan
        fields = (
            'name', 'description', 'monthly_price_ngn', 'yearly_price_ngn',
            'features', 'is_active',
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            'id', 'plan', 'billing_cycle', 'amount_paid', 'status',
            'start_date_utc', 'end_date_utc', 'created_at',
            'renewal_attempts', 'last_renewal_attempt_at', 'cancelled_at',
        )
        read_only_fields = fields


class SubscribeSerializer(serializers.Serializer):
    """
    Validates a subscription request.
    """
    plan_id = serializers.UUIDField()
    billing_cycle = serializers.ChoiceField(
        choices=Subscription.BillingCycle.choices
    )
    payment_method = serializers.ChoiceField(
        choices=[PaymentMethod.WALLET, PaymentMethod.DIRECT]
    )
    # Only required when payment_method is DIRECT
    provider = serializers.ChoiceField(
        choices=['paystack', 'stripe'],
        required=False,
    )

    def validate(self, attrs):
        if attrs['payment_method'] == PaymentMethod.DIRECT and not attrs.get('provider'):
            raise serializers.ValidationError(
                {'provider': 'provider is required for direct payments.'}
            )
        return attrs


class SwitchPlanSerializer(serializers.Serializer):
    """
    Validates a plan switch request.
    """
    plan_id = serializers.UUIDField()
    billing_cycle = serializers.ChoiceField(
        choices=Subscription.BillingCycle.choices
    )
    payment_method = serializers.ChoiceField(
        choices=[PaymentMethod.WALLET, PaymentMethod.DIRECT]
    )
    # Only required when payment_method is DIRECT
    provider = serializers.ChoiceField(
        choices=['paystack', 'stripe'],
        required=False,
    )
    return_url = serializers.URLField(required=False)

    def validate(self, attrs):
        if attrs['payment_method'] == PaymentMethod.DIRECT and not attrs.get('provider'):
            raise serializers.ValidationError(
                {'provider': 'provider is required for direct payments.'}
            )
        return attrs
