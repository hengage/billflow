import logging
import stripe
from django.conf import settings
from api_response.exceptions import ThirdPartyServiceError, NonRetryableProviderError

from payments.constants import Currency
from utils.currency import to_minor

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeProvider:
    """
    Handles all direct interaction with the Stripe API.
    Stripe's SDK handles the HTTP layer — we handle the error classification.

    Reference: https://stripe.com/docs/api
    """

    @classmethod
    def initiate_payment(cls, amount, email, reference, purpose, additional_metadata=None):
        """
        Creates a Stripe PaymentIntent and returns the client_secret.
        The client uses the client_secret with Stripe.js or the mobile SDK
        to complete the payment on their end.

        Raises NonRetryableProviderError for card errors and invalid requests.
        Raises ThirdPartyServiceError for transient Stripe API errors.
        """
        metadata = {
            'reference': str(reference),
            'purpose': purpose,
            **(additional_metadata or {}),
        }

        try:
            intent = stripe.PaymentIntent.create(
                amount=to_minor(amount, Currency.USD),
                currency='usd',
                receipt_email=email,
                metadata=metadata,
                # Idempotency key on the Stripe side too — prevents Stripe
                # from creating duplicate PaymentIntents if we call twice
                idempotency_key=str(reference),
            )
            return {
                'client_secret': intent.client_secret,
                'provider_ref': intent.id,
            }

        except stripe.error.CardError as exc:
            # Card was declined — permanent rejection.
            logger.warning(
                f'Stripe card error | ref={reference} | '
                f'code={exc.code} | message={str(exc)}'
            )
            raise NonRetryableProviderError(str(exc))

        except stripe.error.InvalidRequestError as exc:
            # Our request was malformed in some way — permanent rejection.
            logger.warning(
                f'Stripe invalid request | ref={reference} | message={str(exc)}'
            )
            raise NonRetryableProviderError(str(exc))

        except stripe.error.AuthenticationError as exc:
            # Our API key is invalid — this is a configuration error,
            # not a transient failure. Treat as non-retryable.
            logger.error(
                f'Stripe authentication error | ref={reference} | message={str(exc)}'
            )
            raise NonRetryableProviderError('Payment provider authentication failed.')

        except (stripe.error.APIConnectionError, stripe.error.APIError) as exc:
            # Network error or Stripe server error — transient, worth retrying
            logger.error(
                f'Stripe transient error | ref={reference} | message={str(exc)}'
            )
            raise ThirdPartyServiceError()

    @classmethod
    def verify_signature(cls, payload_bytes, signature):
        """
        Verifies a Stripe webhook signature using the Stripe SDK.

        Stripe's SDK handles the verification internally via construct_event.

        Raises stripe.error.SignatureVerificationError if invalid.
        The caller is responsible for catching this and returning 400.

        Reference: https://stripe.com/docs/webhooks/signatures
        """
        return stripe.Webhook.construct_event(
            payload_bytes,
            signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )