from django.urls import path

from .views import (
    PremiumStatusView,
    PremiumActivateView,
    PremiumHistoryView,
)

urlpatterns = [

    path(
        "status/",
        PremiumStatusView.as_view(),
        name="premium-status",
    ),

    path(
        "activate/",
        PremiumActivateView.as_view(),
        name="premium-activate",
    ),

    path(
        "history/",
        PremiumHistoryView.as_view(),
        name="premium-history",
    ),
]