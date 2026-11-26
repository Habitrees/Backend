from django.db import models

# Create your models here.

from django.conf import settings
from django.db import models
import uuid
class Reminder(models.Model):

    challenge = models.ForeignKey(
        "challenges.Challenge",
        on_delete=models.CASCADE,
        related_name="reminders",
    )

    local_time = models.TimeField()

    message = models.CharField(
        max_length=250,
        blank=True,
        default="",
    )

    enabled = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        ordering = ["local_time", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "challenge",
                    "local_time",
                ],
                name="unique_challenge_reminder_time",
            ),
        ]

    def __str__(self):

        return (
            f"{self.challenge.title} - "
            f"{self.local_time}"
        )

class NotificationPreference(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )

    in_app_enabled = models.BooleanField(
        default=True
    )

    push_enabled = models.BooleanField(
        default=False
    )

    email_reports_enabled = models.BooleanField(
        default=False
    )

    telegram_reports_enabled = models.BooleanField(
        default=False
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )
    smart_reports_enabled = models.BooleanField(
        default=False
    )
    def __str__(self):

        return str(self.user)


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)


class ReminderDelivery(models.Model):
    reminder = models.ForeignKey(Reminder, null=True, on_delete=models.SET_NULL)
    local_date = models.DateField()
    delivered_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["reminder", "local_date"], name="unique_reminder_delivery_day",
        )]

class ReportEmail(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_email",
    )

    email = models.EmailField()

    verification_nonce = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )