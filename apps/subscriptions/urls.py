from django.urls import path
from .views import (
    PlanListCreateView,
    PlanDetailView,
    SubscribeView,
    MySubscriptionView,
    CancelSubscriptionView,
    AdminSubscriptionListView,
)

urlpatterns = [
    path('plans/', PlanListCreateView.as_view(), name='plan-list-create'),
    path('plans/<uuid:pk>/', PlanDetailView.as_view(), name='plan-detail'),
    path('', SubscribeView.as_view(), name='subscribe'),
    path('me/', MySubscriptionView.as_view(), name='my-subscription'),
    path('cancel/', CancelSubscriptionView.as_view(), name='cancel-subscription'),
    path('admin/', AdminSubscriptionListView.as_view(), name='admin-subscription-list'),
]
