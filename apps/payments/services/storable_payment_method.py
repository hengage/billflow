from dataclasses import dataclass


@dataclass
class StorablePaymentMethod:
    """
    Provider-agnostic data structure for storing payment methods.

    Each provider's extractor returns this shape or None if the
    payment method shouldn't be stored (e.g., not reusable).
    """
    authorization_code: str       # Paystack: authorization_code, Stripe: payment_method_id
    provider_customer_id: str     # Paystack: customer_code, Stripe: customer_id (cus_xxx)
    billing_email: str            # The email tied to this authorization
    signature: str                # Deduplication key — unique per card per provider
    last_four: str
    card_brand: str
    exp_month: str
    exp_year: str
    bank: str
    card_type: str
