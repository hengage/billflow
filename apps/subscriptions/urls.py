from django.urls import path
from .views import (
    PlanListView,
    SubscribeView,
    MySubscriptionView,
    CancelSubscriptionView,
    SwitchPlanView,
)

urlpatterns = [
    path('plans/', PlanListView.as_view(), name='plan-list'),
    path('', SubscribeView.as_view(), name='subscribe'),
    path('me/', MySubscriptionView.as_view(), name='my-subscription'),
    path('cancel/', CancelSubscriptionView.as_view(), name='cancel-subscription'),
    path('switch-plan/', SwitchPlanView.as_view(), name='switch-plan'),
]
