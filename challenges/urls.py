
from rest_framework.routers import DefaultRouter

from .views import (
    ChallengeViewSet,
    GardenView,
    DashboardView,
)
from django.urls import path
from .public_views import PublicChallengeViewSet

router = DefaultRouter()

router.register(
    r"challenges",
    ChallengeViewSet,
    basename="challenge",
)

router.register("public-challenges", PublicChallengeViewSet, basename="public-challenge")

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
