import logging
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError

from api_response.exceptions import ThirdPartyServiceError, NonRetryableProviderError, ConflictError
from payments.models import IdempotencyKey, Payment
from payments.constants import IdempotencyRecoveryPoint, PaymentProvider

logger = logging.getLogger(__name__)

# A lock older than this threshold is considered stale — the worker that
# acquired it must have crashed. Recovery takes over when this threshold
# is exceeded. 60 seconds gives a generous buffer beyond typical provider
# response times while still recovering promptly from crashes.
STALE_LOCK_SECONDS = 60


class PaymentProcessor:
    """
    Orchestrates the payment initiation lifecycle using Brandur's
    atomic phases pattern.

    Reference: https://brandur.org/idempotency-keys

    The use of three separate, short-lived transactions as checkpoints,
    with the external provider call happening in the gap between tx2 and tx4.

    The four phases:
        tx1 (STARTED)   → acquire or resume the idempotency key
        tx2 (PAYMENT_CREATED)  → create the Payment record
        tx3 (payment provider call) → call the payment provider — outside any database transaction
        tx4 (FINISHED)  → store the terminal response

    Both success and non-retryable failure advance to FINISHED.
    Only transient failures leave the key at PAYMENT_CREATED for retry.
    If the server crashes between any two phases, the next retry resumes
    from the last committed checkpoint using the stored recovery_point.
    """

    def __init__(self, user, idempotency_key_value, request_path, request_params):
        self.user = user
        # The key value and path together form the uniqueness scope.
        # The client generates the key; the path prevents cross-endpoint collisions.
        self.key_value = str(idempotency_key_value)
        self.request_path = request_path
        self.request_params = request_params

    def execute(self):
        """
        Entry point. Drives the state machine from the current recovery
        point through to FINISHED, resuming from wherever a previous
        attempt left off.
        """
        # Fast-track: check if this key is already finished before acquiring
        # any locks. 
        # This is the common path for retries of completed requests —
        idem_key = IdempotencyKey.objects.filter(
            key=self.key_value,
            user=self.user,
            request_path=self.request_path,
        ).first()

        if idem_key and idem_key.recovery_point == IdempotencyRecoveryPoint.FINISHED:
            return idem_key.response_body, idem_key.response_code

        # tx1 — atomically create or resume the idempotency key
        idem_key = self._acquire_key()

        # Re-check after locking — handles the race between the fast-track
        # read above and the lock acquisition in _acquire_key
        if idem_key.recovery_point == IdempotencyRecoveryPoint.FINISHED:
            return idem_key.response_body, idem_key.response_code

        # tx2 — create the Payment record if we haven't already.
        # If recovery_point is already PAYMENT_CREATED, a previous attempt
        # completed tx2 before crashing — skip straight to the provider call.
        if idem_key.recovery_point == IdempotencyRecoveryPoint.STARTED:
            idem_key = self._create_payment_record(idem_key)

        # Fetch the Payment record created in tx2 via the reverse OneToOne relation
        payment = idem_key.payment

        # --- Foreign state mutation — OUTSIDE any transaction ---
        # This is the dangerous stretch. If the server crashes here, tx2 has
        # already committed — we have a PAYMENT_CREATED key and a PENDING payment.
        # A background reconciliation job finds these and calls the provider's
        # verify endpoint to determine what actually happened.
        try:
            # tx3 — call the provider
            provider_data = self._call_provider(payment)

        except NonRetryableProviderError as exc:
            # The provider permanently rejected the payment.
            # Finalise the key with the error response — future retries will
            # replay this rejection immediately without calling the provider.
            logger.warning(
                f'Non-retryable provider rejection | '
                f'key={self.key_value} | payment={payment.id} | reason={str(exc)}'
            )
            return self._finalise(
                idem_key=idem_key,
                response_body={'error': str(exc), 'provider': payment.provider},
                response_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        except ThirdPartyServiceError:
            # Transient provider failure — leave at PAYMENT_CREATED.
            # The client retries with the same key and we try the provider again.
            logger.error(
                f'Retryable provider failure | '
                f'key={self.key_value} | payment={payment.id} | '
                f'provider={payment.provider}'
            )
            raise

        # tx3 — provider call succeeded — store the response and mark finished
        return self._finalise(
            idem_key=idem_key,
            response_body=provider_data,
            response_code=status.HTTP_200_OK,
        )

    def _acquire_key(self):
        """
        tx1 — Atomically create a new idempotency key or lock an existing one.

        By attempting the INSERT first and catching IntegrityError, we use
        PostgreSQL's own constraint enforcement as the lock. Only one INSERT
        can win. The loser catches IntegrityError and falls through to
        SELECT FOR UPDATE, which blocks until the winner's transaction commits.
        This is atomically correct with zero application-level timing windows.
        """
        with transaction.atomic():
            try:
                idem_key = IdempotencyKey.objects.create(
                    key=self.key_value,
                    user=self.user,
                    request_path=self.request_path,
                    request_params=self.request_params,
                    recovery_point=IdempotencyRecoveryPoint.STARTED,
                    locked_at=timezone.now(),
                )
                logger.info(f'Idempotency key created | key={self.key_value}')
                return idem_key

            except IntegrityError:
                # Key already exists — lock it and inspect its state
                idem_key = IdempotencyKey.objects.select_for_update().get(
                    key=self.key_value,
                    user=self.user,
                    request_path=self.request_path,
                )

                # If the client sent the same key with different req body (req parameters),
                # that's a misuse of the idempotency system. The server rejects it outright.
                # A new key should be generated for a different payment attempt.
                if idem_key.request_params != self.request_params:
                    raise ValidationError(
                        'Idempotency key reused with different request parameters. '
                        'Generate a new key for a different payment attempt.'
                    )

                stale_threshold = timezone.now() - timedelta(seconds=STALE_LOCK_SECONDS)

                if idem_key.locked_at and idem_key.locked_at > stale_threshold:
                    # The lock is recent — another worker is actively processing.
                    # Tell the client to back off and retry in a few seconds.
                    raise ConflictError('This request is currently being processed.')

                # The lock is stale — the previous worker must have crashed.
                # Refresh the lock timestamp and resume from the last checkpoint.
                idem_key.locked_at = timezone.now()
                idem_key.save(update_fields=['locked_at'])

                logger.info(
                    f'Resuming stale key | key={self.key_value} | '
                    f'recovery_point={idem_key.recovery_point}'
                )
                return idem_key

    def _create_payment_record(self, idem_key):
        """
        tx2 — Create the Payment record and advance to PAYMENT_CREATED.

        This is a deliberately separate transaction from tx1. It commits
        independently, creating a durable checkpoint before we attempt
        the external provider call. If the server crashes after this but
        before tx3, a reconciliation job can find PAYMENT_CREATED keys
        and query the provider to determine what happened.
        """
        with transaction.atomic():
            Payment.objects.create(
                user=self.user,
                amount=self.request_params['amount'],
                currency=self.request_params.get('currency', 'NGN'),
                purpose=self.request_params['purpose'],
                provider=self.request_params['provider'],
                idempotency_key=idem_key,
            )

            idem_key.recovery_point = IdempotencyRecoveryPoint.PAYMENT_CREATED
            idem_key.save(update_fields=['recovery_point'])

        # Refresh to get the updated state from the database.
        # Without this, idem_key.payment would not be accessible yet
        # because the OneToOne relation wasn't populated until the Payment
        # was saved inside the transaction that just committed.
        idem_key.refresh_from_db()
        return idem_key

    def _call_provider(self, payment):
        """
        The foreign state mutation — calls the appropriate payment gateway.

        No transaction.atomic() wrapping here — deliberately.
        This method must never hold a database connection open while
        waiting for an HTTP response from an external service.

        Propagates NonRetryableProviderError and ThirdPartyServiceError
        to the caller without catching them — the caller decides what
        to do based on which type it receives.
        """
        from payments.services.providers.paystack import PaystackProvider
        from payments.services.providers.stripe import StripeProvider

        if payment.provider == PaymentProvider.PAYSTACK:
            return PaystackProvider.initiate_payment(
                amount=payment.amount,
                email=payment.user.email,
                reference=str(payment.id),
                purpose=payment.purpose,
            )

        if payment.provider == PaymentProvider.STRIPE:
            return StripeProvider.initiate_payment(
                amount=payment.amount,
                email=payment.user.email,
                reference=str(payment.id),
                purpose=payment.purpose,
            )

        raise ValueError(f'Unsupported provider: {payment.provider}')

    def _finalise(self, idem_key, response_body, response_code):
        """
        tx4 — Store the terminal response and advance the key to FINISHED.

        Called for BOTH success and non-retryable failure outcomes.
        After this transaction commits, the fast-track check at the top
        of execute() will catch all future retries and return the stored
        response immediately.
        """
        with transaction.atomic():
            idem_key.recovery_point = IdempotencyRecoveryPoint.FINISHED
            idem_key.response_code = response_code
            idem_key.response_body = response_body
            idem_key.save(update_fields=['recovery_point', 'response_code', 'response_body'])

        idem_key.refresh_from_db()
        return idem_key.response_body, idem_key.response_code
