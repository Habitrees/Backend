
from rest_framework.routers import DefaultRouter

from .views import (
    ChallengeViewSet,
    GardenView,
    DashboardView,
)
from django.urls import path

router = DefaultRouter()

router.register(
    r"challenges",
    ChallengeViewSet,
    basename="challenge",
)

urlpatterns = [
    path(
        "garden/",
        GardenView.as_view(),
        name="garden",
    ),
    path(
        "dashboard/",
        DashboardView.as_view(),
        name="dashboard",
    ),
] + router.urls
