"""
Brevo (formerly Sendinblue) email provider.
"""
import logging
import requests
from typing import List, Optional
from django.conf import settings
from .base import EmailProvider

logger = logging.getLogger(__name__)


class BrevoProvider(EmailProvider):
    """
    Brevo email provider implementation.
    Uses Brevo REST API v3.
    """
    
    API_URL = "https://api.brevo.com/v3/smtp/email"
    
    @property
    def name(self) -> str:
        return 'brevo'
    
    def __init__(self):
        self.api_key = getattr(settings, 'BREVO_API_KEY', None)
        self.default_from = getattr(settings, 'DEFAULT_FROM_EMAIL', 'BillFlow <noreply@billflow.app>')
        
        if not self.api_key:
            logger.warning("BREVO_API_KEY not configured - emails will fail")
    
    def _get_headers(self) -> dict:
        """Get request headers with API key."""
        return {
            'accept': 'application/json',
            'api-key': self.api_key,
            'content-type': 'application/json',
        }
    
    def send(
        self,
        to: List[str],
        subject: str,
        html_content: str,
        from_email: Optional[str] = None,
        tags: Optional[dict] = None
    ) -> Optional[str]:
        """
        Send email via Brevo API.
        
        Reference: https://developers.brevo.com/reference/sendtransacemail
        """
        if not self.api_key:
            raise RuntimeError("BREVO_API_KEY not configured")
        
        sender = self._parse_from_email(from_email or self.default_from)
        
        payload = {
            'sender': sender,
            'to': [{'email': email} for email in to],
            'subject': subject,
            'htmlContent': html_content,
        }
        
        # Add tags as custom headers if provided
        if tags:
            payload['headers'] = {f'X-Tag-{k}': str(v) for k, v in tags.items()}
        
        try:
            response = requests.post(
                self.API_URL,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            message_id = data.get('messageId')
            
            logger.info(
                f"Email sent via Brevo | message_id={message_id} | "
                f"to={len(to)} recipients | subject={subject[:50]}"
            )
            
            return message_id
            
        except requests.exceptions.HTTPError as exc:
            error_data = exc.response.json() if exc.response else {}
            logger.error(
                f"Brevo API error | status={exc.response.status_code if exc.response else 'unknown'} | "
                f"error={error_data.get('message', str(exc))}"
            )
            raise
            
        except requests.exceptions.RequestException as exc:
            logger.error(f"Brevo request failed | error={str(exc)}")
            raise
    
    def send_batch(
        self,
        emails: List[dict]
    ) -> List[Optional[str]]:
        """
        Send batch of emails via Brevo.
        Brevo doesn't have a true batch endpoint, so we send individually.
        """
        results = []
        
        for email in emails:
            try:
                message_id = self.send(
                    to=email['to'],
                    subject=email['subject'],
                    html_content=email['html_content'],
                    from_email=email.get('from_email'),
                    tags=email.get('tags')
                )
                results.append(message_id)
            except Exception as exc:
                logger.error(f"Failed to send batch email | error={str(exc)}")
                results.append(None)
        
        return results
    
    @staticmethod
    def _parse_from_email(from_email: str) -> dict:
        """
        Parse 'Name <email@domain.com>' format into Brevo sender dict.
        """
        if '<' in from_email and '>' in from_email:
            name = from_email.split('<')[0].strip()
            email = from_email.split('<')[1].split('>')[0].strip()
            return {'name': name, 'email': email}
        return {'email': from_email}
