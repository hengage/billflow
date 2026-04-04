from decimal import Decimal


# Minor unit multipliers per currency.
MINOR_UNIT_MULTIPLIERS = {
    'NGN': Decimal('100'),  # 1 Naira = 100 Kobo
    'USD': Decimal('100'),  # 1 Dollar = 100 Cents
}

DEFAULT_MULTIPLIER = Decimal('100')


def to_minor(amount, currency='NGN'):
    """
    Converts a major unit amount to minor units for payment provider APIs.
    Payment providers (Paystack, Stripe) always expect amounts in minor units.

    Examples:
        to_minor(Decimal('5000'), 'NGN') → 500000  (NGN 5,000 = 500,000 kobo)
        to_minor(Decimal('42.30'), 'USD') → 4230   (USD 42.30 = 4230 cents)

    Args:
        amount: Decimal amount in major units
        currency: ISO 4217 currency code

    Returns:
        int
    """
    multiplier = MINOR_UNIT_MULTIPLIERS.get(currency.upper(), DEFAULT_MULTIPLIER)
    return int(Decimal(str(amount)) * multiplier)


def to_major(amount, currency='NGN'):
    """
    Converts a minor unit amount from payment provider webhooks to major units.
    Provider webhook payloads always send amounts in minor units.

    Examples:
        to_major(500000, 'NGN') → Decimal('5000.00')  (500,000 kobo = NGN 5,000)
        to_major(4230, 'USD')   → Decimal('42.30')    (4230 cents = USD 42.30)

    Args:
        amount: int amount in minor units (from provider payload)
        currency: ISO 4217 currency code

    Returns:
        Decimal — always Decimal to stay compatible with DecimalField
    """
    multiplier = MINOR_UNIT_MULTIPLIERS.get(currency.upper(), DEFAULT_MULTIPLIER)
    return (Decimal(str(amount)) / multiplier).quantize(Decimal('0.01'))
