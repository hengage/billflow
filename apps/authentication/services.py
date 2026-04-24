from django.db import transaction
from django.contrib.auth import get_user_model
from notifications.services import NotificationService
from notifications.constants import NotificationType

User = get_user_model()


class AuthService:
    """
    Service for authentication-related operations.
    """

    @classmethod
    def register_user(cls, email: str, first_name: str, last_name: str, password: str) -> User:
        """
        Register a new user and stage welcome email notification to outbox.
        
        Both user creation and outbox write happen in the same transaction,
        ensuring exactly-once notification delivery via the outbox pattern.
        
        Args:
            email: User's email address
            first_name: User's first name
            last_name: User's last name  
            password: Raw password (will be hashed)
            
        Returns:
            The newly created User instance
            
        Raises:
            ValueError: If user with email already exists
        """
        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            
            cls._enqueue_welcome_notification(user)
            
            return user

    @staticmethod
    def _enqueue_welcome_notification(user: User) -> None:
        """
        Stage welcome email notification to outbox.
        
        Called within same transaction as user creation.
        The outbox drainer will pick this up and send the actual email.
        """
        NotificationService.enqueue_to_outbox(
            user=user,
            notification_type=NotificationType.WELCOME,
            subject='Welcome to BillFlow!',
            template_name='welcome',
            context={
                'user': {
                    'first_name': user.first_name,
                },
            },
        )
