"""
Shared Celery utilities for retry logic with exponential backoff and jitter.

These utilities help prevent thundering herd problems when retrying failed tasks
by spreading retries randomly across the backoff window.
"""

import random

MAX_RETRIES = 5
BASE_DELAY = 60
MAX_DELAY = 3600


def backoff_with_jitter(retry_number):
    """
    Calculates retry delay using exponential backoff with full jitter.

    Full jitter spreads retries randomly across the backoff window, 
    reducing peak load on the server.

    Formula: random(0, min(cap, base * 2^n))
    Reference: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
    """
    exponential = BASE_DELAY * (2 ** retry_number)
    capped = min(MAX_DELAY, exponential)
    return random.uniform(0, capped)
