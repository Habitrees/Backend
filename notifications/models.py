from django.db import models

# Create your models here.

from django.conf import settings
from django.db import models

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

    def __str__(self):

        return str(self.user)