from functools import wraps
from http import HTTPStatus
from django.http import JsonResponse
from django.core.cache import cache
from api_response.responses import build_envelope
from payments.constants import (
    PAYMENT_INFLIGHT_KEY,
    PAYMENT_CAPACITY_LIMIT_KEY,
    DEFAULT_PAYMENT_CAPACITY,
    PAYMENT_COUNTER_TTL_SECONDS,
)
from utils.messages import get_message


def payment_capacity_limiter(view_func):
    """
    Applies Little's Law (L = λW) to the payment initiation endpoint
    by capping the number of concurrent in-flight requests.

    When the system is at capacity, clients receive a 503 error
    rather than experiencing degraded latency as the
    request queues behind database lock contention or slow provider calls.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        raw_limit = cache.get(PAYMENT_CAPACITY_LIMIT_KEY, DEFAULT_PAYMENT_CAPACITY)
        try:
            max_capacity = int(raw_limit)
        except (ValueError, TypeError):
            max_capacity = DEFAULT_PAYMENT_CAPACITY

        try:
            current = cache.incr(PAYMENT_INFLIGHT_KEY)
        except ValueError:
            # Key missing — first request after startup or after TTL expiry.
            cache.add(PAYMENT_INFLIGHT_KEY, 1, timeout=PAYMENT_COUNTER_TTL_SECONDS)
            current = 1

        if current > max_capacity:
            # Over capacity — decrement immediately so we don't permanently
            # reduce the available capacity by one for every rejected request.
            cache.decr(PAYMENT_INFLIGHT_KEY)
            response = JsonResponse(
                build_envelope(
                    data=None,
                    message=get_message('CAPACITY_EXCEEDED', 'PAYMENT'),
                    error={'detail': get_message('TOO_MANY_REQUESTS', 'PAYMENT')},
                    url=request.path,
                ),
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            # Retry-After tells the client how many seconds to wait before
            # retrying. This prevents thundering herd.
            response['Retry-After'] = '30'
            return response

        try:
            return view_func(request, *args, **kwargs)
        finally:
            # Decrement unconditionally. Without the finally block, every
            # exception would permanently consume one capacity slot.
            cache.decr(PAYMENT_INFLIGHT_KEY)

    return wrapped
