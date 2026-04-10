import logging
from django.db import transaction

from payments.constants import (
    Currency,
    PaymentProvider,
    PaymentStatus,
    PaymentPurpose,
    PaystackEvent,
    StripeEvent,
)
from payments.models import Payment, WebhookLog
from utils.currency import to_major

logger = logging.getLogger(__name__)


class WebhookHandler:
    """
    Owns all webhook processing logic for both Paystack and Stripe.

    This class is the single place in the codebase that knows:
    - How to extract the reference and event type from each provider's payload
    - What to do when a payment succeeds or fails
    - Which downstream services to call based on the payment's purpose
    """

    @classmethod
    def process(cls, webhook_log_id, provider):
        """
        Entry point called by the Celery task.
        Fetches the WebhookLog and dispatches to the correct provider handler.
        """
        try:
            webhook_log = WebhookLog.objects.get(id=webhook_log_id)
        except WebhookLog.DoesNotExist:
            # This should never happen — the view creates the log before
            # queuing the task. If it does, there's nothing to process.
            logger.error(
                f'WebhookLog not found | id={webhook_log_id}'
            )
            return

        # Guard against double-processing — if a task is retried after a
        # transient failure but the previous attempt actually succeeded,
        # we don't want to process the same event twice.
        if webhook_log.processed:
            logger.info(
                f'Webhook already processed, skipping | id={webhook_log_id}'
            )
            return

        if provider == PaymentProvider.PAYSTACK:
            cls._process_paystack(webhook_log)
        elif provider == PaymentProvider.STRIPE:
            cls._process_stripe(webhook_log)
        else:
            logger.error(f'Unknown provider | provider={provider}')

    # -------------------------------------------------------------------------
    # Provider-specific dispatchers
    # These methods know each provider's payload shape and extract the
    # relevant fields before delegating to the shared handlers below.
    # -------------------------------------------------------------------------

    @classmethod
    def _process_paystack(cls, webhook_log):
        """
        Extracts Paystack-specific fields from the payload and routes
        to the appropriate handler based on the event type.

        Paystack payload structure:
        {
            "event": "charge.success",
            "data": {
                "reference": "...",   ← our Payment UUID
                "amount": 500000,     ← in kobo (NGN * 100)
                "authorization": {
                    "last4": "4081",
                    "brand": "visa"
                },
                "metadata": {...}
            }
        }
        """
        payload = webhook_log.payload
        event_type = payload.get('event')
        data = payload.get('data', {})

        # The reference Paystack sends back is the UUID we passed when
        # initiating the payment 
        reference = data.get('reference')

        if event_type == PaystackEvent.CHARGE_SUCCESS:
            cls._handle_success(
                reference=reference,
                amount=to_major(data.get('amount', 0), 'NGN'),
                last_four=data.get('authorization', {}).get('last4', ''),
                card_brand=data.get('authorization', {}).get('brand', ''),
                metadata=data.get('metadata', {}),
                raw_data=data,
                provider=PaymentProvider.PAYSTACK,
                webhook_log=webhook_log,
            )

        else:
            logger.info(
                f'Unhandled Paystack event | '
                f'event={event_type} | log={webhook_log.id}'
            )
            webhook_log.processed = True
            webhook_log.save(update_fields=['processed'])

    @classmethod
    def _process_stripe(cls, webhook_log):
        """
        Extracts Stripe-specific fields from the payload and routes
        to the appropriate handler based on the event type.

        Stripe payload structure:
        {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_...",          ← provider_ref we stored
                    "amount_received": 5000,  ← in cents (USD * 100)
                    "metadata": {...}
                }
            }
        }
        """
        payload = webhook_log.payload
        event_type = payload.get('type')
        intent = payload.get('data', {}).get('object', {})
        reference = intent.get('metadata', {}).get('reference')

        if event_type == StripeEvent.PAYMENT_INTENT_SUCCEEDED:
            cls._handle_success(
                reference=reference,
                amount=to_major(intent.get('amount_received', 0), Currency.USD),
                # Stripe card details come in a separate charge object,
                # not directly in the PaymentIntent — leave blank for now
                last_four='',
                card_brand='',
                metadata=intent.get('metadata', {}),
                raw_data=payload,
                provider=PaymentProvider.STRIPE,
                webhook_log=webhook_log,
            )

        elif event_type == StripeEvent.PAYMENT_INTENT_FAILED:
            cls._handle_failure(
                reference=reference,
                webhook_log=webhook_log,
            )

        else:
            logger.info(
                f'Unhandled Stripe event type | '
                f'event={event_type} | log={webhook_log.id}'
            )
            webhook_log.processed = True
            webhook_log.save(update_fields=['processed'])

    # -------------------------------------------------------------------------
    # Shared handlers
    # These methods contain the actual business logic — they don't know or
    # care which provider sent the event. By the time execution reaches here,
    # the reference has been extracted and the amount has been normalised.
    # -------------------------------------------------------------------------

    @staticmethod
    def _mark_permanently_failed(webhook_log, reference, reason):
        """
        Marks a webhook as permanently failed to prevent infinite retry churn.
        Called when the payment reference cannot be found or other unrecoverable errors.
        """
        logger.error(
            f'{reason} | ref={reference} | marking log={webhook_log.id} as permanently failed'
        )
        webhook_log.permanently_failed = True
        webhook_log.failure_reason = f'{reason} for reference: {reference}'
        webhook_log.save(update_fields=['permanently_failed', 'failure_reason'])

    @classmethod
    def _handle_success(cls, reference, amount, last_four, card_brand, metadata, raw_data, provider, webhook_log):
        """
        Processes a successful payment event.

        The notification task is queued via transaction.on_commit() so
        it only fires if the transaction successfully commits. This prevents
        the user receiving a "payment successful" email for a transaction
        that the database actually rolled back.
        """
        with transaction.atomic():
            try:
                # select_for_update locks this Payment row for the duration
                # of the transaction — prevents concurrent webhook deliveries
                # for the same event from both trying to process it simultaneously.
                payment = Payment.objects.select_for_update().get(id=reference)
            except Payment.DoesNotExist:
                cls._mark_permanently_failed(
                    webhook_log, reference, 'Payment record not found'
                )
                return

            # Idempotency guard — Payment providers can send the same
            # webhook more than once. If we already processed this payment,
            # mark the log as processed and return cleanly without re-crediting.
            if payment.status == PaymentStatus.SUCCESS:
                logger.info(f'Payment already processed, skipping | ref={reference}')
                webhook_log.processed = True
                webhook_log.save(update_fields=['processed'])
                return

            # Update the Payment record with the confirmed status and card details.
            # PCI DSS: we only store last_four and card_brand — never the full number.
            payment.status = PaymentStatus.SUCCESS
            payment.last_four = last_four
            payment.card_brand = card_brand
            payment.save(update_fields=['status', 'last_four', 'card_brand', 'updated_at'])

            # Trigger the downstream action that this payment was initiated for.
            # The purpose was stored on the Payment record at initiation time,
            if payment.purpose == PaymentPurpose.WALLET_TOPUP:
                cls._activate_wallet_topup(payment, amount)

            elif payment.purpose == PaymentPurpose.SUBSCRIPTION:
                cls._activate_subscription(payment, metadata)

            # Store authorization for recurring charges if applicable
            cls._store_payment_method_if_applicable(payment, raw_data, provider)

            webhook_log.processed = True
            webhook_log.save(update_fields=['processed'])

        # Queue notification after the transaction commits —
        from payments.tasks import send_payment_success_notification
        user = payment.user
        transaction.on_commit(
            lambda: send_payment_success_notification.delay(
                user_id=str(user.id),
                payment_id=str(payment.id),
            )
        )

    @classmethod
    def _handle_failure(cls, reference, webhook_log):
        """
        Processes a failed payment event.
        Marks the Payment as FAILED and queues a failure notification.
        No wallet or subscription changes.
        """
        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(id=reference)
            except Payment.DoesNotExist:
                cls._mark_permanently_failed(
                    webhook_log, reference, 'Payment record not found'
                )
                return

            # Idempotency guard — same as success handler
            if payment.status == PaymentStatus.FAILED:
                webhook_log.processed = True
                webhook_log.save(update_fields=['processed'])
                return

            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=['status', 'updated_at'])

            webhook_log.processed = True
            webhook_log.save(update_fields=['processed'])

        from payments.tasks import send_payment_failed_notification
        user = payment.user
        transaction.on_commit(
            lambda: send_payment_failed_notification.delay(
                user_id=str(user.id),
                payment_id=str(payment.id),
            )
        )

    @staticmethod
    def _store_payment_method_if_applicable(payment, raw_data, provider):
        """
        Stores a reusable payment method for future recurring charges.

        Provider-agnostic dispatcher — each provider extracts its own
        payment method data according to its payload structure.
        """
        from payments.models import StoredPaymentMethod
        from payments.services.providers.paystack import PaystackProvider

        extractors = {
            PaymentProvider.PAYSTACK: PaystackProvider.extract_storable_method,
        }

        extractor = extractors.get(provider)
        if not extractor:
            return

        storable = extractor(raw_data)
        if not storable:
            return

        StoredPaymentMethod.objects.get_or_create(
            user=payment.user,
            signature=storable.signature,
            provider=provider,
            defaults={
                'authorization_code': storable.authorization_code,
                'provider_customer_id': storable.provider_customer_id,
                'billing_email': storable.billing_email,
                'last_four': storable.last_four,
                'card_brand': storable.card_brand,
                'exp_month': storable.exp_month,
                'exp_year': storable.exp_year,
                'bank': storable.bank,
                'card_type': storable.card_type,
                'is_reusable': True,
            }
        )

    # -------------------------------------------------------------------------
    # Downstream activation helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _activate_wallet_topup(payment, amount):
        """
        Credits the user's wallet after a successful top-up payment.
        Called inside the atomic block in _handle_success, so if this
        raises an exception the entire transaction rolls back — the Payment
        status update and the wallet credit succeed or fail together.
        """
        from wallets.service import WalletService
        WalletService.credit(
            user=payment.user,
            amount=amount,
            reference=str(payment.id),
        )

    @staticmethod
    def _activate_subscription(payment, metadata):
        """
        Activates a subscription after a successful payment.
        plan_id was stored in the payment metadata at initiation time.
        """
        plan_id = metadata.get('plan_id')
        if not plan_id:
            logger.error(
                f'plan_id missing from payment metadata | payment={payment.id}'
            )
            return

        from subscriptions.services import SubscriptionService
        SubscriptionService.activate(
            user=payment.user,
            plan_id=plan_id,
            payment=payment,
        )
