"""
Seed default subscription plans.
Usage: python manage.py seed_plans
"""
from django.core.management.base import BaseCommand
from subscriptions.models import Plan


class Command(BaseCommand):
    help = 'Seed default subscription plans'

    def handle(self, *args, **options):
        plans = [
            {
                'name': 'Free',
                'description': 'Perfect for trying out BillFlow. Limited to basic features.',
                'monthly_price_ngn': 0,
                'yearly_price_ngn': 0,
                'features': [
                    '5 invoices per month',
                    'Basic invoice templates',
                    'Email support',
                    'Single user',
                ],
                'is_active': True,
            },
            {
                'name': 'Starter',
                'description': 'For freelancers and solo entrepreneurs who need more flexibility.',
                'monthly_price_ngn': 5000,
                'yearly_price_ngn': 50000,
                'features': [
                    '50 invoices per month',
                    'All invoice templates',
                    'Priority email support',
                    'Basic financial reports',
                    'Custom branding',
                ],
                'is_active': True,
            },
            {
                'name': 'Pro',
                'description': 'For growing businesses that need automation and team collaboration.',
                'monthly_price_ngn': 15000,
                'yearly_price_ngn': 150000,
                'features': [
                    'Unlimited invoices',
                    'Advanced templates with custom fields',
                    'Priority support (chat + email)',
                    'Advanced analytics & reports',
                    'API access',
                    'Up to 5 team members',
                    'Recurring invoices',
                    'Multi-currency support',
                ],
                'is_active': True,
            },
            {
                'name': 'Enterprise',
                'description': 'For large organizations with custom requirements and dedicated support.',
                'monthly_price_ngn': 50000,
                'yearly_price_ngn': 500000,
                'features': [
                    'Everything in Pro',
                    'White-label solution',
                    'Dedicated account manager',
                    'Custom integrations',
                    'SLA guarantee',
                    'Unlimited team members',
                    'Advanced security features',
                    'On-premise deployment option',
                ],
                'is_active': True,
            },
        ]

        created_count = 0
        for plan_data in plans:
            plan, created = Plan.objects.get_or_create(
                name=plan_data['name'],
                defaults=plan_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created plan: {plan.name}')
                )
                created_count += 1
            else:
                self.stdout.write(
                    self.style.WARNING(f'Plan already exists: {plan.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nDone! Created {created_count} new plan(s).')
        )
