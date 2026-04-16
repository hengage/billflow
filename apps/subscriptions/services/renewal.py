"""
RenewalProcessor - Orchestrates subscription auto-renewal with idempotency.

Mirrors PaymentProcessor pattern for consistency:
- Four-phase execution with crash recovery
- Idempotency key management
- Provider call abstraction
- State finalization

Usage:
    RenewalProcessor(subscription_id).execute()
"""
import logging
from datetime import timedelta
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import status

from subscriptions.models import Subscription
from payments.models import IdempotencyKey, Payment
from payments.constants import (
    IdempotencyRecoveryPoint,
    PaymentStatus,
    PaymentPurpose,
    PaymentProvider,
    Currency,
)
from api_response.exceptions import PaymentDeclined

logger = logging.getLogger(__name__)

STALE_LOCK_SECONDS = 60  # 1 minute threshold for stale locks
MAX_RENEWAL_ATTEMPTS = 3


class RenewalProcessor:
    """
    Orchestrates subscription auto-renewal with idempotency and crash recovery.

    Four-phase pattern:
    1. Atomic: Create/get IdempotencyKey, acquire lock
    2. Atomic: Create PENDING Payment record (checkpoint before foreign call)
    3. Foreign: Call payment provider (NO transaction)
    4. Webhook: On confirmation, mark Payment SUCCESS, renew subscription

    The processor handles:
    - Concurrency via select_for_update and idempotency key locking
    - Crash recovery via recovery_point checks
    - Provider call abstraction
    - State finalization and counter increments
    """

    def __init__(self, subscription_id):
        self.subscription_id = subscription_id
        self.subscription = None
        self.idem_key = None
        self.key_value = None
        self.payment = None
        self.amount = None
        self.next_attempt = None

    def execute(self):
        """
        Main entry point. Executes the 4-phase renewal flow.

        Phases:
        1. Acquire - Lock subscription, get/create idempotency key
        2. Create - Create PENDING Payment record, lookup stored method
        3. Call - Charge stored method via provider (outside transaction)
        4. Finalize - Mark idempotency key FINISHED, handle success/decline

        Returns:
            None (side effects: payment created, provider called)

        Raises:
            Exception: Transient errors for Celery retry
        """
        # Phase 1: Acquire subscription lock and idempotency key
        self._phase_1_acquire()

        # Phase 2: Create payment record (if not already created)
        self._phase_2_create_payment()

        # Phase 3: Call provider (outside transaction - foreign state mutation)
        provider_result = self._phase_3_call_provider()

        # Phase 4: Finalize based on provider result (atomic)
        self._phase_4_finalize(provider_result)

    # -------------------------------------------------------------------------
    # PHASE 1: Acquire subscription lock and idempotency key
    # -------------------------------------------------------------------------

    def _phase_1_acquire(self):
        """
        Atomically locks subscription and creates/acquires idempotency key.

        Uses nested atomic blocks to handle IntegrityError on key creation.
        """
        with transaction.atomic():
            # Lock subscription with skip_locked to avoid waiting
            self.subscription = Subscription.objects.select_for_update(
                skip_locked=True
            ).filter(
                id=self.subscription_id,
                status=Subscription.Status.ACTIVE,
            ).select_related('plan', 'user').first()

            if not self.subscription:
                # Already processed by another worker or not active
                return

            # Calculate next attempt number for key generation
            self.next_attempt = self.subscription.renewal_attempts + 1
            self.key_value = f"renewal-{self.subscription_id}-v{self.next_attempt}"

            # Calculate amount based on billing cycle
            plan = self.subscription.plan
            if self.subscription.billing_cycle == Subscription.BillingCycle.MONTHLY:
                self.amount = plan.monthly_price_ngn
            else:
                self.amount = plan.yearly_price_ngn

            # Create or acquire idempotency key
            self._acquire_key()

    def _acquire_key(self):
        """
        Creates or acquires an idempotency key with proper locking.

        Pattern: inner atomic for create (savepoint), outer for the whole operation.
        Handles race conditions via IntegrityError catch and lock inspection.
        """
        try:
            with transaction.atomic():  # savepoint
                self.idem_key = IdempotencyKey.objects.create(
                    user=self.subscription.user,
                    key=self.key_value,
                    request_path="subscriptions.services.renewal.RenewalProcessor",
                    request_params={
                        'subscription_id': str(self.subscription_id),
                        'attempt_number': self.next_attempt,
                    },
                    recovery_point=IdempotencyRecoveryPoint.STARTED,
                    locked_at=timezone.now(),
                )
        except IntegrityError:
            # Key already exists - lock it and inspect its state
            self.idem_key = IdempotencyKey.objects.select_for_update().get(
                user=self.subscription.user,
                key=self.key_value,
                request_path="subscriptions.services.renewal.RenewalProcessor",
            )

            # Check if already finished
            if self.idem_key.recovery_point == IdempotencyRecoveryPoint.FINISHED:
                logger.info(f"Renewal attempt already completed: {self.subscription_id}")
                return

            # Check for stale lock (another worker died mid-processing)
            stale_threshold = timezone.now() - timedelta(seconds=STALE_LOCK_SECONDS)
            if self.idem_key.locked_at and self.idem_key.locked_at > stale_threshold:
                # Another worker is actively processing - skip
                logger.info(
                    f"Renewal attempt {self.next_attempt} for subscription "
                    f"{self.subscription_id} is being processed by another worker"
                )
                return

            # Update lock for this attempt
            self.idem_key.locked_at = timezone.now()
            self.idem_key.save(update_fields=['locked_at'])

    # -------------------------------------------------------------------------
    # PHASE 2: Create payment record
    # -------------------------------------------------------------------------

    def _get_stored_payment_method(self, payment=None):
        """
        Gets stored payment method for renewal.

        If payment provided (resumption/crash recovery): restore from payment metadata.
        Otherwise (fresh attempt): lookup best available method.

        Priority for fresh lookup:
        1. Default method (is_default=True, reusable, active)
        2. Most recently stored reusable method (fallback)

        Raises PaymentDeclined if no suitable method exists.
        """
        from payments.models import StoredPaymentMethod

        if payment:
            # Resumption: restore from payment metadata
            stored_method_id = payment.metadata.get('stored_method_id')
            if not stored_method_id:
                raise PaymentDeclined('Payment missing stored_method_id in metadata.')

            try:
                return StoredPaymentMethod.objects.get(
                    id=stored_method_id,
                    user=self.subscription.user,
                    is_active=True,
                )
            except StoredPaymentMethod.DoesNotExist:
                raise PaymentDeclined('Stored payment method no longer available.')

        # Fresh lookup: try default first
        stored_method = StoredPaymentMethod.objects.filter(
            user=self.subscription.user,
            is_default=True,
            is_reusable=True,
            is_active=True,
        ).first()

        if not stored_method:
            # Fall back to most recently stored
            stored_method = StoredPaymentMethod.objects.filter(
                user=self.subscription.user,
                is_reusable=True,
                is_active=True,
            ).order_by('-created_at').first()

        if not stored_method:
            logger.warning(
                f'No stored payment method for renewal | '
                f'user={self.subscription.user.id} | sub={self.subscription_id}'
            )
            raise PaymentDeclined('No stored payment method available for renewal.')

        return stored_method

    def _phase_2_create_payment(self):
        """
        Creates PENDING Payment record before provider call.

        If recovery_point is STARTED, lookup stored payment method and create payment.
        If already PAYMENT_CREATED (crash recovery), restore state from existing payment.
        """
        import uuid

        if not self.idem_key:
            return

        if self.idem_key.recovery_point == IdempotencyRecoveryPoint.STARTED:
            from payments.utils import generate_payment_reference

            with transaction.atomic():
                self.stored_method = self._get_stored_payment_method()
                provider = self.stored_method.provider
                currency = Currency.NGN if provider == PaymentProvider.PAYSTACK else Currency.USD

                self.payment = Payment.objects.create(
                    user=self.subscription.user,
                    amount=self.amount,
                    currency=currency,
                    provider=provider,
                    purpose=PaymentPurpose.RENEW_SUBSCRIPTION,
                    status=PaymentStatus.PENDING,
                    idempotency_key=self.idem_key,
                    reference=generate_payment_reference(),
                    metadata={
                        'attempt_number': self.next_attempt,
                        'stored_method_id': str(self.stored_method.id),
                        'subscription_id': str(self.subscription.id),
                    },
                )
                self.idem_key.recovery_point = IdempotencyRecoveryPoint.PAYMENT_CREATED
                self.idem_key.save(update_fields=['recovery_point'])
        else:
            # Crash recovery - restore from existing payment
            self.payment = self.idem_key.payment
            self.stored_method = self._get_stored_payment_method(self.payment)

    # -------------------------------------------------------------------------
    # PHASE 3: Call provider
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_provider_charger(provider):
        """
        Strategy pattern: Returns the appropriate charge method for the provider.

        Each provider implements charge_stored(stored_method, amount, reference,
        purpose, metadata) with a unified interface.
        """
        from payments.services.providers.paystack import PaystackProvider
        from payments.services.providers.stripe import StripeProvider

        chargers = {
            PaymentProvider.PAYSTACK: PaystackProvider.charge_stored,
            PaymentProvider.STRIPE: StripeProvider.charge_stored,
        }
        return chargers.get(provider)

    def _phase_3_call_provider(self):
        """
        Phase 3: Calls payment provider to charge stored method.

        NO transaction - foreign state mutation.
        Returns dict with result info for Phase 4 finalization.
        Raises on transient errors for Celery retry.
        """
        if not self.payment:
            return None

        charger = self._get_provider_charger(self.stored_method.provider)
        if not charger:
            raise PaymentDeclined(
                f'Provider {self.stored_method.provider} not supported for stored charges.'
            )

        try:
            provider_data = charger(
                stored_method=self.stored_method,
                amount=self.amount,
                reference=self.payment.reference,
                purpose=PaymentPurpose.RENEW_SUBSCRIPTION,
                metadata={
                    'attempt_number': self.next_attempt,
                },
            )

            return {
                'success': True,
                'provider_data': provider_data,
            }

        except PaymentDeclined as exc:
            return {
                'success': False,
                'declined': True,
                'error': str(exc),
            }

    def _phase_4_finalize(self, provider_result):
        """
        Phase 4: Finalizes the renewal attempt based on provider result.

        Atomic - updates idempotency key and handles success/decline outcomes.
        """
        from notifications.services import NotificationService

        if not provider_result:
            return

        if provider_result['success']:
            # Success path - finalize and log
            self._finalize(
                response_code=status.HTTP_200_OK,
                response_body=provider_result['provider_data'],
            )
            logger.info(
                f"Renewal charge initiated: {self.subscription_id} | "
                f"payment={self.payment.id} | awaiting webhook confirmation"
            )
        else:
            # Decline path - mark payment failed, finalize, notify
            self.payment.status = PaymentStatus.FAILED
            self.payment.save(update_fields=['status'])

            self._finalize(
                response_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                response_body={
                    'error': provider_result['error'],
                    'provider': self.payment.provider,
                },
            )

            # Refresh to get updated renewal_attempts from finalize
            self.subscription.refresh_from_db()

            # Notify user of failed renewal
            attempts_remaining = MAX_RENEWAL_ATTEMPTS - self.subscription.renewal_attempts
            NotificationService.send_renewal_failed(
                user=self.subscription.user,
                subscription=self.subscription,
                attempts_remaining=attempts_remaining,
            )
            logger.warning(
                f"Renewal declined: {self.subscription_id}, "
                f"attempt {self.subscription.renewal_attempts}, "
                f"{attempts_remaining} remaining"
            )

    # -------------------------------------------------------------------------
    # FINALIZATION
    # -------------------------------------------------------------------------

    def _finalize(self, response_code, response_body):
        """
        Finalizes the idempotency key and increments renewal counter.

        Called after definite success or non-retryable failure.
        """
        with transaction.atomic():
            self.idem_key.recovery_point = IdempotencyRecoveryPoint.FINISHED
            self.idem_key.response_code = response_code
            self.idem_key.response_body = response_body
            self.idem_key.save(update_fields=[
                'recovery_point', 'response_code', 'response_body'
            ])

            # Increment renewal attempt counter
            self.subscription.renewal_attempts += 1
            self.subscription.last_renewal_attempt_at = timezone.now()
            self.subscription.save(update_fields=[
                'renewal_attempts', 'last_renewal_attempt_at'
            ])
