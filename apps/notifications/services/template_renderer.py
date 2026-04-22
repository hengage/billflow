"""
Email template rendering using Django's template engine.
"""
from django.template.loader import render_to_string
from typing import Dict, Any


class TemplateRenderer:
    """
    Renders email templates with context data.
    Uses Django's template engine for HTML email rendering.
    """
    
    # Template mapping - maps notification types to template paths
    TEMPLATES = {
        # Payment templates
        'payment_success': 'emails/payments/success.html',
        'payment_failed': 'emails/payments/failed.html',
        
        # Wallet templates
        'wallet_topup': 'emails/wallet/topup.html',
        
        # Subscription templates
        'subscription_activated': 'emails/subscriptions/activated.html',
        'subscription_renewed': 'emails/subscriptions/renewed.html',
        'subscription_expiring': 'emails/subscriptions/expiring.html',
        'subscription_expired': 'emails/subscriptions/expired.html',
        'subscription_cancelled': 'emails/subscriptions/cancelled.html',
        'plan_switched': 'emails/subscriptions/plan_switched.html',
        'renewal_failed': 'emails/subscriptions/renewal_failed.html',
        
        # User templates
        'welcome': 'emails/users/welcome.html',
    }
    
    @classmethod
    def render(cls, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render an email template with context.
        
        Args:
            template_name: Template identifier (e.g., 'payment_success')
            context: Dictionary of variables for the template
            
        Returns:
            Rendered HTML string
        """
        template_path = cls.TEMPLATES.get(template_name)
        
        if not template_path:
            # Fallback to plain text if template not found
            return cls._render_plain_text(template_name, context)
        
        try:
            return render_to_string(template_path, context)
        except Exception as exc:
            # Fallback to plain text on template error
            return cls._render_plain_text(template_name, context, error=str(exc))
    
    @classmethod
    def _render_plain_text(cls, template_name: str, context: Dict[str, Any], error: str = None) -> str:
        """
        Fallback plain text renderer when HTML template is unavailable.
        """
        lines = [
            f"BillFlow Notification: {template_name.replace('_', ' ').title()}",
            "=" * 50,
            "",
        ]
        
        for key, value in context.items():
            if value:
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
        
        if error:
            lines.extend(["", f"Template Error: {error}"])
        
        lines.extend(["", "Thank you for using BillFlow!"])
        
        # Convert to simple HTML
        html_lines = ['<p>' + line + '</p>' if line else '<br>' for line in lines]
        return '\n'.join([
            '<!DOCTYPE html><html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">',
            *html_lines,
            '</body></html>'
        ])
