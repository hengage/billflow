from django.core.cache import cache
from django.core.management.base import BaseCommand

from payments.constants import PAYMENT_CAPACITY_LIMIT_KEY


class Command(BaseCommand):
    """
    Sets the payment capacity limit across all servers.

    Uses Redis to propagate the change instantly.
    The decorator checks this value on every request.

    Examples:
        python manage.py set_payment_capacity 250
        python manage.py set_payment_capacity 500
        railway run python manage.py set_payment_capacity 300
    """
    help = 'Set the max concurrent payment requests capacity'

    def add_arguments(self, parser):
        parser.add_argument(
            'capacity',
            type=int,
            help='Maximum number of concurrent in-flight payment requests',
        )

    def handle(self, *args, **options):
        capacity = options['capacity']

        if capacity < 1:
            self.stderr.write(self.style.ERROR('Capacity must be at least 1'))
            return

        cache.set(PAYMENT_CAPACITY_LIMIT_KEY, capacity, timeout=None)
        self.stdout.write(
            self.style.SUCCESS(
                f'Payment capacity set to {capacity} concurrent requests'
            )
        )
