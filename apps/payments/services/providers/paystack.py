import hmac
import hashlib
import logging
import requests
from django.conf import settings
from api_response.exceptions import ThirdPartyServiceError, NonRetryableProviderError
from payments.constants import PAYSTACK_NON_RETRYABLE_STATUS_CODES
from utils.currency import to_minor
from utils.messages import PAYMENT_MESSAGES

logger = logging.getLogger(__name__)


class PaystackProvider:
    """
    Handles all direct interaction with the Paystack API.

    Reference: https://paystack.com/docs/api/
    """
    BASE_URL = 'https://api.paystack.co'

    @classmethod
    def _get_headers(cls):
        return {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }

    @classmethod
    def initiate_payment(cls, amount, email, reference, purpose, additional_metadata=None):
        """
        Calls Paystack's transaction initialize endpoint and returns the
        authorization_url for the user to complete payment.

        Raises NonRetryableProviderError for permanent rejections (4xx from Paystack).
        Raises ThirdPartyServiceError for transient failures (network errors, 5xx).

        The reference we pass to Paystack is our Payment model's UUID
        """
        payload = {
            'email': email,
            'amount': to_minor(amount),
            'reference': str(reference),
            'metadata': {
                'reference': str(reference),
                'purpose': purpose,
                **(additional_metadata or {}),
            },
        }

        try:
            response = requests.post(
                f'{cls.BASE_URL}/transaction/initialize',
                json=payload,
                headers=cls._get_headers(),
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            # Network-level failure — connection refused, DNS failure, timeout.
            logger.error(
                f'Paystack connection error | ref={reference} | error={str(exc)}'
            )
            raise ThirdPartyServiceError()

        if response.status_code in PAYSTACK_NON_RETRYABLE_STATUS_CODES:
            # Paystack understood our request but rejected it for a business
            # reason. This will not change on retry — finalise the key with
            # this failure rather than leaving it open for retry.
            error_message = response.json().get('message', PAYMENT_MESSAGES['FAILED'])
            logger.warning(
                f'Paystack permanent rejection | ref={reference} | '
                f'status={response.status_code} | message={error_message}'
                f'API Status: {response.status_code}'
            )
            raise NonRetryableProviderError(error_message)

        if response.status_code >= 500:
            # Paystack server error — transient, worth retrying
            logger.error(
                f'Paystack server error | ref={reference} | '
                f'status={response.status_code}'
                f'API Status: {response.status_code}'
            )
            raise ThirdPartyServiceError()

        data = response.json()
        if not data.get('status'):
            # Paystack returned 200 but with status=false in the body.
            # This is a logical failure — treat as non-retryable since
            # a well-formed request shouldn't produce this on retry.
            logger.warning(
                f'Paystack logical failure | ref={reference} | '
                f'message={data.get("message")}'
                f'API Status: {response.status_code}'
            )
            raise NonRetryableProviderError(data.get('message', PAYMENT_MESSAGES['FAILED']))

        return {
            'checkout_url': data['data']['authorization_url'],
            'reference': data['data']['reference'],
        }

    @classmethod
    def verify_signature(cls, payload_bytes, signature):
        """
        Verifies a Paystack webhook signature using HMAC-SHA512.

        Paystack sends the signature in the X-Paystack-Signature header.
        We compute our own HMAC over the raw request body using our secret key.
        If they match, the event genuinely came from Paystack — not a spoofed request.

        Reference: https://paystack.com/docs/payments/webhooks/#verify-event-origin
        """
        if not signature:
            return False

        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
            payload_bytes,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    @classmethod
    def verify_transaction(cls, reference):
        """
        Queries Paystack directly for the status of a transaction.
        Used by the verify endpoint and by reconciliation jobs that need
        to determine what happened to a payment that's stuck in PENDING.
        """
        try:
            response = requests.get(
                f'{cls.BASE_URL}/transaction/verify/{reference}',
                headers=cls._get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(
                f'Paystack verification failed | ref={reference} | error={str(exc)}'
            )
            raise ThirdPartyServiceError()

    @staticmethod
    def extract_storable_method(data):
        """
        Extracts a storable payment method from a Paystack charge.success payload.
        Returns None if the authorization is not reusable.

        Paystack uses an explicit 'reusable' flag on the authorization object.
        Only cards marked reusable can be charged recurrently.

        Reference: https://paystack.com/docs/payments/recurring-charges/
        """
        from payments.services.storable_payment_method import StorablePaymentMethod

        authorization = data.get('authorization', {})

        # Paystack's explicit reusability flag — check before storing
        if not authorization.get('reusable'):
            return None

        signature = authorization.get('signature', '')
        if not signature:
            return None

        return StorablePaymentMethod(
            authorization_code=authorization.get('authorization_code', ''),
            provider_customer_id=data.get('customer', {}).get('customer_code', ''),
            billing_email=data.get('customer', {}).get('email', ''),
            signature=signature,
            last_four=authorization.get('last4', ''),
            card_brand=authorization.get('brand', ''),
            exp_month=authorization.get('exp_month', ''),
            exp_year=authorization.get('exp_year', ''),
            bank=authorization.get('bank', ''),
            card_type=authorization.get('card_type', ''),
        )