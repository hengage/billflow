import logging
import stripe
from django.conf import settings
from api_response.exceptions import ThirdPartyServiceError

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeProvider:
    """
    Handles Stripe PaymentIntent creation for USD transactions.
    """

    @classmethod
    def initiate_payment(cls, amount, email, reference, purpose, additional_metadata=None):
        metadata = {
            "payment_reference": str(reference),
            "payment_purpose": purpose,
        }
        if additional_metadata:
            metadata.update(additional_metadata)

        try:
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),
                currency="usd",
                receipt_email=email,
                metadata=metadata
            )

            return {
                "client_secret": intent.client_secret,
                "provider_ref": intent.id 
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error | Ref: {reference} | Error: {str(e)}")
            # Use default exception message to hide gateway details from user
            raise ThirdPartyServiceError()
