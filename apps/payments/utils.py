"""Utility functions for payments app."""
import uuid
from datetime import datetime


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
