# Cache keys
PLANS_LIST_CACHE_KEY = 'plans_list'
PLANS_LIST_CACHE_TTL = 60 * 30  # 30 minutes

USER_SUBSCRIPTION_CACHE_KEY_PREFIX = 'user_subscription'
USER_SUBSCRIPTION_CACHE_TTL = 60 * 5  # 5 minutes


class PaymentMethod:
    WALLET = 'wallet'
    DIRECT = 'direct'
