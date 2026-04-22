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
    """
    from django.conf import settings
    
    provider_name = getattr(settings, 'EMAIL_PROVIDER', 'console')
    
    providers = {
        'console': ConsoleProvider,
        'brevo': BrevoProvider,
    }
    
    provider_class = providers.get(provider_name, ConsoleProvider)
    return provider_class()
