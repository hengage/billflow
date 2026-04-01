import hmac
import hashlib
import logging
import requests
from django.conf import settings
from api_response.exceptions import ThirdPartyServiceError

logger = logging.getLogger(__name__)


class PaystackProvider:
    """
    Handles direct interaction with the Paystack API for NGN transactions.
    """
    BASE_URL = "https://api.paystack.co"

    @classmethod
    def _get_headers(cls):
        return {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    @classmethod
    def verify_signature(cls, payload_bytes, signature):
        """
        Verifies Paystack webhook HMAC-SHA512 signature.
        Uses hmac.compare_digest to prevent timing attacks.
        """
        if not signature:
            return False
            
        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
            payload_bytes,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)

    @classmethod
    def initiate_payment(cls, amount, email, reference, purpose, additional_metadata=None):
        url = f"{cls.BASE_URL}/transaction/initialize"
        headers = cls._get_headers()
        
        metadata = {
            "payment_reference": str(reference),
            "payment_purpose": purpose,
        }
        if additional_metadata:
            metadata.update(additional_metadata)
            
        payload = {
            "amount": int(amount * 100), 
            "email": email,
            "reference": str(reference),
            "metadata": metadata
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status() 
            data = response.json()

            if not data.get('status'):
                logger.error(f"Paystack logical failure | Ref: {reference} | Msg: {data.get('message')}")
                raise ThirdPartyServiceError()

            return {
                "checkout_url": data['data']['authorization_url'],
                "provider_ref": data['data']['reference']
            }
            
        except requests.RequestException as e:
            logger.error(f"Paystack connection error | Ref: {reference} | Error: {str(e)}")
            raise ThirdPartyServiceError()

    @classmethod
    def verify_transaction(cls, reference):
        """
        Direct API check for transaction status. 
        Used as a fallback if webhooks are delayed.
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
            logger.error(f"Paystack verification failed | Ref: {reference} | Error: {str(exc)}")
            raise ThirdPartyServiceError()
