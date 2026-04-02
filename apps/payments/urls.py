from django.urls import path
from .views import (
    InitiatePaymentView,
    PaystackWebhookView,
    PaystackVerifyView,
    StripeWebhookView,
    PaymentHistoryView,
)

urlpatterns = [
    path('initiate/', InitiatePaymentView.as_view(), name='payment-initiate'),
    path('paystack/webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),
    path('paystack/verify/<str:reference>/', PaystackVerifyView.as_view(), name='paystack-verify'),
    path('stripe/webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('history/', PaymentHistoryView.as_view(), name='payment-history'),
]
