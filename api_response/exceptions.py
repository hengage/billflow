from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.exceptions import APIException

"""Custom API exceptions and exception handler.

DRF Exceptions API reference:
https://www.django-rest-framework.org/api-guide/exceptions
"""


class ThirdPartyServiceError(APIException):
    """Use when an upstream/third-party dependency is unavailable.

    Intended for cases like Stripe downtime/timeouts or any external API failure
    where the client should retry later.

    DRF reference:
    https://www.django-rest-framework.org/api-guide/exceptions/#api-reference
    """
    status_code = 503
    default_detail = 'Service temporarily unavailable, try again later.'
    default_code = 'third_party_service_unavailable'


class NonRetryableProviderError(APIException):
    """
    Raised when a payment provider permanently rejects a payment.
    Examples: invalid card number, account not found, currency not supported.

    The processor will finalise the idempotency key with the error response
    so the client gets the same rejection on every retry without re-calling
    the provider. There is no point retrying — the outcome will not change.
    """
    status_code = 422
    default_detail = 'Payment was permanently rejected by the provider.'
    default_code = 'payment_rejected'


class PaymentDeclined(NonRetryableProviderError):
    """
    Raised when a provider explicitly declines a charge.
    Specifically for recurring charge attempts - card declined, insufficient funds etc.
    """
    status_code = 422
    default_detail = 'Payment was declined.'
    default_code = 'payment_declined'


class ConflictError(APIException):
    """
    Raised when a request conflicts with another in-flight request.
    The client should back off and retry after a short delay.
    """
    status_code = 409
    default_detail = 'This request is currently being processed.'
    default_code = 'conflict'


def custom_exception_handler(exc, context):
    """Wrap DRF exception responses in the project's standard response envelope."""
    response = exception_handler(exc, context)

    if response is not None:
        data = response.data
        request = context.get("request")
        payload = {
            "status": False,
            "data": None,
            "url": request.path if request else None,
            "error": data,
        }

        # Include top-level messages if provided
        if isinstance(data, dict) and "detail" in data:
            payload["message"] = data["detail"]

        return Response(payload, status=response.status_code)

    return response
