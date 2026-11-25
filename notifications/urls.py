
from django.urls import path

from rest_framework.routers import DefaultRouter

from .views import (
    ReminderViewSet,
    NotificationPreferenceView,
)

router = DefaultRouter()

router.register(
    r"reminders",
    ReminderViewSet,
    basename="reminder",
)

urlpatterns = [

    path(
        "notification-preferences/",
        NotificationPreferenceView.as_view(),
        name="notification-preferences",
    ),

] + router.urls