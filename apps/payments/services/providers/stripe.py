import logging
import stripe
from django.conf import settings
from api_response.exceptions import ThirdPartyServiceError, NonRetryableProviderError, PaymentDeclined

from payments.constants import Currency
from utils.currency import to_minor
from utils.messages import PAYMENT_MESSAGES

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeProvider:
    """
    Handles all direct interaction with the Stripe API.

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
            # Request was malformed in some way — permanent rejection.
            logger.warning(
                f'Stripe invalid request | ref={reference} | message={str(exc)}'
            )
            raise NonRetryableProviderError(str(exc))

        except stripe.error.AuthenticationError as exc:
            # API key is invalid — this is a configuration error,
            # not a transient failure. Treat as non-retryable.
            logger.error(
                f'Stripe authentication error | ref={reference} | message={str(exc)}'
            )
            raise NonRetryableProviderError(PAYMENT_MESSAGES['FAILED'])

        except (stripe.error.APIConnectionError, stripe.error.APIError) as exc:
            # Network error or Stripe server error — transient, worth retrying
            logger.error(
                f'Stripe transient error | ref={reference} | message={str(exc)}'
            )
            raise ThirdPartyServiceError()

    @classmethod
    def charge_stored_method(cls, payment_method_id, customer_id, amount, reference, purpose, metadata=None):
        """
        Charges a stored payment method for recurring payments.
        Used by RenewalProcessor for subscription auto-renewal.

        Creates a PaymentIntent with off_session=True for recurring charges.
        The payment_method_id is the stored card token (pm_xxx).
        The customer_id is required for off-session charges.

        Reference: https://stripe.com/docs/payments/save-during-payment
        """
        from payments.constants import Currency
        from utils.currency import to_minor

        try:
            intent = stripe.PaymentIntent.create(
                amount=to_minor(amount, Currency.USD),
                currency='usd',
                customer=customer_id,
                payment_method=payment_method_id,
                off_session=True,
                confirm=True,
                metadata={
                    'reference': str(reference),
                    'purpose': purpose,
                    **(metadata or {}),
                },
                idempotency_key=str(reference),
            )

            return {
                'provider_ref': intent.id,
                'status': intent.status,
                'client_secret': intent.client_secret,
            }

        except stripe.error.CardError as exc:
            # Card was declined — permanent rejection for this stored method
            logger.warning(
                f'Stripe stored charge declined | ref={reference} | '
                f'code={exc.code} | message={str(exc)}'
            )
            raise PaymentDeclined(str(exc))

        except stripe.error.InvalidRequestError as exc:
            # Invalid payment_method or customer — permanent
            logger.warning(
                f'Stripe stored charge invalid request | ref={reference} | message={str(exc)}'
            )
            raise PaymentDeclined(str(exc))

        except stripe.error.AuthenticationError as exc:
            logger.error(
                f'Stripe auth error | ref={reference} | message={str(exc)}'
            )
            raise PaymentDeclined('Payment configuration error.')

        except (stripe.error.APIConnectionError, stripe.error.APIError) as exc:
            # Transient errors — retryable
            logger.error(
                f'Stripe stored charge transient error | ref={reference} | message={str(exc)}'
            )
            raise ThirdPartyServiceError()

    @classmethod
    def charge_stored(cls, stored_method, amount, reference, purpose, metadata=None):
        """
        Strategy interface for charging a stored payment method.
        Delegates to charge_stored_method with Stripe-specific field mapping.
        """
        return cls.charge_stored_method(
            payment_method_id=stored_method.authorization_code,
            customer_id=stored_method.provider_customer_id,
            amount=amount,
            reference=reference,
            purpose=purpose,
            metadata=metadata,
        )

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

    @staticmethod
    def extract_storable_method(data):
        """
        Extracts storable payment method data from Stripe webhook payload.

        Called by WebhookHandler when processing a successful payment.
        Returns a StorablePaymentMethod dataclass or None if not storable.

        For Stripe, we extract from the PaymentIntent's charges.data[0].payment_method_details
        """
        from payments.services.storable_payment_method import StorablePaymentMethod

        try:
            # Stripe webhook data structure for payment_intent.succeeded
            payment_intent = data.get('data', {}).get('object', {})

            # Only store card payments
            charges = payment_intent.get('charges', {}).get('data', [])
            if not charges:
                return None

            charge = charges[0]
            payment_method_details = charge.get('payment_method_details', {})
            if payment_method_details.get('type') != 'card':
                return None

            card = payment_method_details.get('card', {})

            # Get the payment method ID for future charges
            payment_method_id = charge.get('payment_method')
            if not payment_method_id:
                return None

            # Get customer ID for off-session charges
            customer_id = payment_intent.get('customer')
            if not customer_id:
                return None

            # Get billing email from receipt_email or charges
            billing_email = payment_intent.get('receipt_email', '')
            if not billing_email:
                billing_email = charge.get('billing_details', {}).get('email', '')

            # Fingerprint is Stripe's unique identifier for a card (across all Stripe accounts)
            fingerprint = card.get('fingerprint', '')
            if not fingerprint:
                return None

            return StorablePaymentMethod(
                authorization_code=payment_method_id,  # pm_xxx for Stripe
                provider_customer_id=customer_id,        # cus_xxx for Stripe
                billing_email=billing_email,
                signature=fingerprint,                   # Stripe's card fingerprint
                last_four=card.get('last4', ''),
                card_brand=card.get('network', ''),      # visa, mastercard, etc
                exp_month=str(card.get('exp_month', '')),
                exp_year=str(card.get('exp_year', '')),
                bank=card.get('issuer', ''),             # issuing bank if available
                card_type=card.get('funding', ''),       # credit, debit, prepaid
            )

        except (AttributeError, KeyError, TypeError) as exc:
            logger.warning(f'Failed to extract storable method from Stripe webhook: {exc}')
            return None