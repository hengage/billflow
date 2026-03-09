from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings

User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, user_id, subject, message, html_message=None):
    """
    Generic async email task.
    All notification emails go through here.

    Args:
        user_id (str)       — UUID string of the recipient user
        subject (str)       — email subject line
        message (str)       — plain text fallback
        html_message (str)  — HTML email body (optional)
    """
    try:
        user = User.objects.get(id=user_id)

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,  # raise exception on failure so Celery can retry
        )

    except User.DoesNotExist:
        return

    except Exception as exc:
        raise self.retry(exc=exc)
