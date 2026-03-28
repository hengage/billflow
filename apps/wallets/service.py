from django.db import transaction
from .models import Wallet, WalletTransaction


class WalletService:
    """
    All wallet mutations go through this service.
    
    """

    @staticmethod
    def get_balance(user):
        """
        Returns wallet for display.
        This is for READ display only — never use for mutation decisions.
        """
        wallet = Wallet.objects.get(user=user)
        return wallet

    @staticmethod
    def get_transactions(user):
        """
        Returns transaction history for a user's wallet.
        Filtered to the user only.
        """
        transactions = WalletTransaction.objects.filter(
            wallet__user=user
        )
        return transactions

    @staticmethod
    def _validate_sufficient_balance(wallet, amount):
        """
        Validates that wallet has sufficient balance for the deduction.
        
        Args:
            wallet: Wallet instance
            amount: Decimal amount to check
        
        Raises:
            ValueError if insufficient balance
        """
        if wallet.balance < amount:
            raise ValueError(
                f'Insufficient balance. '
                f'Required: {amount} NGN, Available: {wallet.balance} NGN.'
            )

    @staticmethod
    def credit(user, amount, reference):
        """
        Credits the wallet after a successful payment webhook.
        Called by the Paystack/Stripe webhook handler after verifying
        the payment signature and logging to WebhookLog.

        Args:
            user: User instance
            amount: Decimal amount to credit in NGN
            reference: Idempotency key — provider's transaction reference
        
        Returns:
            WalletTransaction instance
        
        Raises:
            ValueError if reference already processed (idempotency check)
        """
        # Idempotency check — if this reference was already processed,
        # the webhook fired twice. Don't credit twice.
        if WalletTransaction.objects.filter(reference=reference).exists():
            raise ValueError(f'Transaction {reference} already processed.')

        with transaction.atomic():
            # select_for_update locks the wallet row until the transaction
            # commits — prevents concurrent credits from reading the same
            # balance and both adding to it (lost update problem)
            wallet = Wallet.objects.select_for_update().get(user=user)
            wallet.balance += amount
            wallet.save(update_fields=['balance', 'updated_at'])

            tx = WalletTransaction.objects.create(
                wallet=wallet,
                amount=amount,
                type=WalletTransaction.TransactionType.TOPUP,
                reference=reference,
            )

        return tx

    @classmethod
    def deduct(cls, user, amount, reference):
        """
        Deducts from wallet for a subscription payment.
        Called by the subscription view when payment_method='wallet'.

        Args:
            user: User instance
            amount: Decimal amount to deduct in NGN
            reference: Idempotency key for this deduction

        Returns:
            WalletTransaction instance

        Raises:
            ValueError if insufficient balance
            ValueError if reference already processed
        """
        if WalletTransaction.objects.filter(reference=reference).exists():
            raise ValueError(f'Transaction {reference} already processed.')

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=user)

            cls._validate_sufficient_balance(wallet, amount)

            wallet.balance -= amount
            wallet.save(update_fields=['balance', 'updated_at'])

            tx = WalletTransaction.objects.create(
                wallet=wallet,
                amount=amount,
                type=WalletTransaction.TransactionType.DEDUCTION,
                reference=reference,
            )

        return tx