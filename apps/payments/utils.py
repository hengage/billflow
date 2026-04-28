"""Utility functions for payments app."""
import logging
import uuid
from datetime import datetime

from rest_framework import status
from rest_framework.exceptions import ValidationError

from api_response.exceptions import ConflictError
from api_response.helpers import fail, success
from utils.messages import PAYMENT_MESSAGES, SYSTEM_MESSAGES

logger = logging.getLogger(__name__)


def generate_payment_reference():
    """
    Generate a unique payment reference.

    Format: YYYYMMDDhhmm_<uuid_first_12_chars>
    Example: 202504160435_a1b2c3d4e5f6

    Returns:
        str: Unique reference for payment provider
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    uuid_part = str(uuid.uuid4()).replace('-', '')[:12]
    return f'{timestamp}_{uuid_part}'


def execute_payment_processor(processor, success_message):
    """
    Execute a PaymentProcessor and return a standardized API response.

    Handles success (200), provider failure (non-200), ConflictError,
    ValidationError, and unexpected exceptions uniformly.

    Args:
        processor: PaymentProcessor instance to execute.
        success_message: Message for the success response.

    Returns:
        APIResponse: fail or success response.
    """
    try:
        response_body, response_code = processor.execute()
        if response_code != status.HTTP_200_OK:
            return fail(
                message=PAYMENT_MESSAGES['FAILED'],
                error=response_body,
                status_code=response_code,
            )
        return success(data=response_body, message=success_message)

    except ConflictError as exc:
        return fail(message=str(exc), status_code=status.HTTP_409_CONFLICT)

    except ValidationError as exc:
        return fail(
            message=str(exc),
            error={'detail': str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    except Exception:
        logger.exception('Payment initiation failed')
        return fail(
            message=SYSTEM_MESSAGES['SERVER_ERROR'],
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
