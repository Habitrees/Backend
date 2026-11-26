
from django.urls import path

from rest_framework.routers import DefaultRouter

from .views import (
    ReminderViewSet,
    NotificationPreferenceView,
)

from .center import NotificationViewSet
from .report_email import (
    ReportEmailView,
    RequestReportEmailView,
    ConfirmReportEmailView,
)
router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

router.register(
    r"reminders",
    ReminderViewSet,
    basename="reminder",
)

urlpatterns = [
    path(
        "report-email/",
        ReportEmailView.as_view(),
        name="report-email",
    ),

    path(
        "report-email/request/",
        RequestReportEmailView.as_view(),
        name="report-email-request",
    ),

    path(
        "report-email/confirm/",
        ConfirmReportEmailView.as_view(),
        name="report-email-confirm",
    ),
    path(
        "notification-preferences/",
        NotificationPreferenceView.as_view(),
        name="notification-preferences",
    ),

] + router.urls