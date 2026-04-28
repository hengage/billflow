from payments.constants import Currency


# Cache keys
PLANS_LIST_CACHE_KEY = 'plans_list'
PLANS_LIST_CACHE_TTL = 60 * 30  # 30 minutes

USER_SUBSCRIPTION_CACHE_KEY_PREFIX = 'user_subscription'
USER_SUBSCRIPTION_CACHE_TTL = 60 * 5  # 5 minutes


def get_plans_list_cache_key(currency: str) -> str:
    return f'{PLANS_LIST_CACHE_KEY}_{currency.upper()}'


def invalidate_plans_list_cache(cache_backend) -> None:
    for currency in Currency.values:
        cache_backend.delete(get_plans_list_cache_key(currency))


class PaymentMethod:
    WALLET = 'wallet'
    DIRECT = 'direct'
