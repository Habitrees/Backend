from django.db import models

# Create your models here.

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
)


class Challenge(models.Model):

    class Polarity(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEGATIVE = "negative", "Negative"

    class Kind(models.TextChoices):
        TIME = "time", "Time"
        COUNT = "count", "Count"
        BINARY = "binary", "Binary"

    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    class Mode(models.TextChoices):
        STRICT = "strict", "Strict"
        FLEXIBLE = "flexible", "Flexible"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenges",
    )

    title = models.CharField(max_length=120)

    description = models.TextField(
        blank=True,
        max_length=2000,
    )

    polarity = models.CharField(
        max_length=8,
        choices=Polarity.choices,
        default=Polarity.POSITIVE,
    )

    kind = models.CharField(
        max_length=8,
        choices=Kind.choices,
    )

    target_value = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    unit = models.CharField(
        max_length=30,
        blank=True,
    )

    start_date = models.DateField()

    duration_days = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(366),
        ],
    )

    frequency = models.CharField(
        max_length=8,
        choices=Frequency.choices,
        default=Frequency.DAILY,
    )

    mode = models.CharField(
        max_length=8,
        choices=Mode.choices,
        default=Mode.STRICT,
    )

    timezone = models.CharField(
        max_length=64,
        default="UTC",
    )

    archived = models.BooleanField(default=False)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at", "-pk"]

        indexes = [
            models.Index(
                fields=["owner", "archived"],
                name="challenge_owner_archive_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    duration_days__gte=1,
                    duration_days__lte=366,
                ),
                name="challenge_valid_duration",
            ),
        ]

    @property
    def end_date(self):
        return self.start_date + timedelta(
            days=self.duration_days - 1
        )

    def __str__(self):
        return self.title


class HabitLog(models.Model):

    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    period_start = models.DateField()

    value = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    performed = models.BooleanField(
        null=True,
        blank=True,
    )

    success = models.BooleanField(
        default=False
    )
    recovered_at = models.DateTimeField(
    null=True,
    blank=True,
    editable=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        ordering = ["-period_start"]

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "challenge",
                    "period_start",
                ],
                name="unique_challenge_period_log",
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(
                        value__isnull=False,
                        performed__isnull=True,
                    )
                    |
                    models.Q(
                        value__isnull=True,
                        performed__isnull=False,
                    )
                ),
                name="habitlog_valid_value_type",
            ),
        ]

    def __str__(self):

        return (
            f"{self.challenge.title} - "
            f"{self.period_start}"
        )
