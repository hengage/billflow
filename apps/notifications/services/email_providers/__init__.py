"""
Email provider implementations.
Supports: console, brevo, aws_ses
"""
from .base import EmailProvider
from .console import ConsoleProvider
from .brevo import BrevoProvider

__all__ = ['EmailProvider', 'ConsoleProvider', 'BrevoProvider', 'get_email_provider']


def get_email_provider():
    """
    Factory function to get the configured email provider.
    Reads EMAIL_PROVIDER setting to determine which provider to use.
    
    Returns:
        EmailProvider instance
    
    Raises:
        ValueError: If EMAIL_PROVIDER is unknown and DEBUG=False
    """
    from django.conf import settings

    provider_name = getattr(settings, 'EMAIL_PROVIDER', 'console')

    providers = {
        'console': ConsoleProvider,
        'brevo': BrevoProvider,
    }

    provider_class = providers.get(provider_name)

    if not provider_class:
        if settings.DEBUG:
            provider_class = ConsoleProvider
        else:
            raise ValueError(
                f"Unknown EMAIL_PROVIDER: '{provider_name}'. "
                f"Valid options: {list(providers.keys())}"
            )

    return provider_class()
