"""
Centralized error and success messages for the application.

This module provides a single source of truth for all user-facing messages,
ensuring consistency across the API and making it easier to update messaging
or add internationalization in the future.
"""

# Wallet messages
WALLET_MESSAGES = {
    'BALANCE_RETRIEVED': 'Wallet balance retrieved.',
    'TOPUP_INITIATED': 'Top-up initiated via {provider}. Complete payment to credit wallet.',
    'TRANSACTIONS_RETRIEVED': 'Transactions retrieved.',
    'INSUFFICIENT_BALANCE': 'You don\'t have enough balance for this transaction.',
    'TOPUP_MAX_LIMIT': 'You can\'t top up more than 1 million at a go.',
    'TOPUP_MIN_LIMIT': 'Minimum top-up is 100.',
    'INVALID_PROVIDER': 'Provider must be either paystack or stripe.',
}

# General validation messages
VALIDATION_MESSAGES = {
    'VALIDATION_FAILED': 'Validation failed.',
    'INVALID_REQUEST': 'Invalid request.',
    'PERMISSION_DENIED': 'You do not have permission to perform this action.',
    'NOT_FOUND': '{resource} not found.',
    'SERVER_ERROR': 'Something went wrong. Please try again later.',
}

# Notification messages
NOTIFICATION_MESSAGES = {
    'NOTIFICATIONS_RETRIEVED': 'Notifications retrieved.',
    'NOTIFICATION_MARKED_READ': 'Notification marked as read.',
    'ALL_NOTIFICATIONS_READ': 'All notifications marked as read.',
    'NOTIFICATION_NOT_FOUND': 'Notification not found.',
}

# Authentication messages
AUTH_MESSAGES = {
    'LOGIN_SUCCESS': 'Login successful.',
    'LOGOUT_SUCCESS': 'Logged out successfully.',
    'REGISTER_SUCCESS': 'Account created successfully.',
    'INVALID_CREDENTIALS': 'Invalid credentials.',
    'TOKEN_REFRESHED': 'Token refreshed successfully.',
    'PASSWORD_RESET_SENT': 'Password reset instructions sent to your email.',
    'PASSWORD_RESET_SUCCESS': 'Password reset successful.',
}


# Payment messages
PAYMENT_MESSAGES = {
    'CAPACITY_EXCEEDED': 'Payment system at capacity. Please retry shortly.',
    'TOO_MANY_REQUESTS': 'Too many concurrent payment requests.',
    'INITIATED': 'Payment initiated successfully.',
    'COMPLETED': 'Payment completed successfully.',
    'FAILED': 'Payment failed.',
    'NOT_FOUND': 'Payment not found.',
}


def get_message(key, category='VALIDATION', **kwargs):
    """
    Retrieve a message by key from the specified category.
    
    Args:
        key: The message key (e.g., 'BALANCE_RETRIEVED')
        category: Message category ('WALLET', 'VALIDATION', 'NOTIFICATION', 'AUTH')
        **kwargs: Format string placeholders
    
    Returns:
        The formatted message string
    
    Example:
        get_message('TOPUP_INITIATED', 'WALLET', provider='paystack')
        # Returns: 'Top-up initiated via paystack. Complete payment to credit wallet.'
    """
    categories = {
        'WALLET': WALLET_MESSAGES,
        'VALIDATION': VALIDATION_MESSAGES,
        'NOTIFICATION': NOTIFICATION_MESSAGES,
        'AUTH': AUTH_MESSAGES,
        'PAYMENT': PAYMENT_MESSAGES,
    }
    
    message_dict = categories.get(category, VALIDATION_MESSAGES)
    message = message_dict.get(key, 'An error occurred.')
    
    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError:
            return message
    return message
