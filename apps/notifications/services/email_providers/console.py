"""
Console email provider - logs emails to console for local development.
"""
import logging
from typing import List, Optional
from .base import EmailProvider

logger = logging.getLogger(__name__)


class ConsoleProvider(EmailProvider):
    """
    Development provider that logs emails to console instead of sending.
    Useful for testing without actually sending emails.
    """
    
    @property
    def name(self) -> str:
        return 'console'
    
    def send(
        self,
        to: List[str],
        subject: str,
        html_content: str,
        from_email: Optional[str] = None,
        tags: Optional[dict] = None
    ) -> Optional[str]:
        """Log email to console."""
        message_id = f"console_{hash(subject + ''.join(to)) % 10000000:07d}"
        
        # Truncate HTML for readability
        html_preview = html_content[:500] + '...' if len(html_content) > 500 else html_content
        
        logger.info(
            f"\n{'='*60}\n"
            f"EMAIL SENT (Console Provider)\n"
            f"{'='*60}\n"
            f"Message ID: {message_id}\n"
            f"From: {from_email or 'default'}\n"
            f"To: {', '.join(to)}\n"
            f"Subject: {subject}\n"
            f"Tags: {tags or {}}\n"
            f"{'-'*60}\n"
            f"HTML Content Preview:\n{html_preview}\n"
            f"{'='*60}"
        )
        
        return message_id
    
    def send_batch(
        self,
        emails: List[dict]
    ) -> List[Optional[str]]:
        """Log batch of emails to console."""
        logger.info(f"Batch send initiated - {len(emails)} emails")
        results = []
        
        for i, email in enumerate(emails, 1):
            logger.info(f"Sending email {i}/{len(emails)}")
            message_id = self.send(
                to=email['to'],
                subject=email['subject'],
                html_content=email['html_content'],
                from_email=email.get('from_email'),
                tags=email.get('tags')
            )
            results.append(message_id)
        
        logger.info(f"Batch complete - {len([r for r in results if r])} sent")
        return results
