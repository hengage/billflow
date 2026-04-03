from functools import wraps
from http import HTTPStatus
from django.http import JsonResponse
from django.core.cache import cache
from api_response.responses import build_envelope

PAYMENT_INFLIGHT_KEY = 'payment_inflight_count'
MAX_PAYMENT_CAPACITY = 100
# Safety net TTL — if a worker process is killed mid-request without
# running the finally block, the counter would drift upward forever.
# A 60-second TTL resets it automatically in that edge case.
COUNTER_TTL_SECONDS = 60


def payment_capacity_limiter(view_func):
    """
    Applies Little's Law (L = λW) to the payment initiation endpoint
    by capping the number of concurrent in-flight requests.

    When the system is at capacity, clients receive a 503 with a
     rather than experiencing degraded latency as the
    request queues behind database lock contention or slow provider calls.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        # Atomically increment and check — single Redis round trip.
        current = cache.incr(PAYMENT_INFLIGHT_KEY)

        # On the very first increment, set the TTL safety net.
        if current == 1:
            cache.expire(PAYMENT_INFLIGHT_KEY, COUNTER_TTL_SECONDS)

        if current > MAX_PAYMENT_CAPACITY:
            # Over capacity — decrement immediately so we don't permanently
            # reduce the available capacity by one for every rejected request.
            cache.decr(PAYMENT_INFLIGHT_KEY)
            response = JsonResponse(
                build_envelope(
                    data=None,
                    message='Payment system at capacity. Please retry shortly.',
                    error={'detail': 'Too many concurrent payment requests.'},
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
