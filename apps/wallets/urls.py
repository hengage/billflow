from django.urls import path
from .views import WalletView, WalletTopUpView, WalletTransactionListView

urlpatterns = [
    path('', WalletView.as_view(), name='wallet'),
    path('topup/', WalletTopUpView.as_view(), name='wallet-topup'),
    path('transactions/', WalletTransactionListView.as_view(), name='wallet-transactions'),
]