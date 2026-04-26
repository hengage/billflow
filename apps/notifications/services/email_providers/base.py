"""
Abstract base class for email providers.
"""
from abc import ABC, abstractmethod
from typing import List, Optional


class EmailProvider(ABC):
    """
    Abstract base class for all email providers.
    Implement this to add support for new email services (Sendi, AWS SES, etc.)
    """
    
    @abstractmethod
    def send(
        self,
        to: List[str],
        subject: str,
        html_content: str,
        from_email: Optional[str] = None,
        tags: Optional[dict] = None
    ) -> Optional[str]:
        """
        Send a single email.
        
        Args:
            to: List of recipient email addresses
            subject: Email subject
            html_content: HTML email body
            from_email: Sender email address (uses default if None)
            tags: Optional metadata/tags for tracking
            
        Returns:
            Message ID if successful, None otherwise
            
        Raises:
            Provider-specific exceptions on failure
        """
        pass
    
    @abstractmethod
    def send_batch(
        self,
        emails: List[dict]
    ) -> List[Optional[str]]:
        """
        Send multiple emails in a batch.
        
        Args:
            emails: List of email dicts with keys: to, subject, html_content, from_email, tags
            
        Returns:
            List of message IDs (None for failed sends)
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging/identification."""
        pass
