
from rest_framework.routers import DefaultRouter

from .views import ChallengeViewSet, GardenView
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
] + router.urls
