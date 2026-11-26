from django.db import models

# Create your models here.

import uuid

from django.conf import settings
from django.db import models
from datetime import timedelta

from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
)

from challenges.models import Challenge

class HabitGroup(models.Model):

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_habit_groups",
    )

    name = models.CharField(max_length=120)

    description = models.TextField(
        blank=True,
        max_length=2000,
    )

    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
    )

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.name

class GroupMembership(models.Model):

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    group = models.ForeignKey(
        HabitGroup,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="habitree_group_memberships",
    )

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER,
    )

    can_manage_members = models.BooleanField(
        default=False
    )

    can_manage_challenges = models.BooleanField(
        default=False
    )

    can_warn_members = models.BooleanField(
        default=False
    )

    joined_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = ["joined_at", "pk"]

        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"],
                name="unique_habit_group_member",
            ),
            models.UniqueConstraint(
                fields=["group"],
                condition=models.Q(role="owner"),
                name="unique_habit_group_owner",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(role="member")
                    | models.Q(
                        can_manage_members=False,
                        can_manage_challenges=False,
                        can_warn_members=False,
                    )
                ),
                name="regular_member_no_admin_permissions",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.group_id}"

class GroupChallenge(models.Model):

    class FailurePolicy(models.TextChoices):
        NONE = "none", "None"
        WARN = "warn", "Warn"
        REMOVE = "remove", "Remove"

    group = models.ForeignKey(
        HabitGroup,
        on_delete=models.CASCADE,
        related_name="challenges",
    )

    title = models.CharField(max_length=120)

    description = models.TextField(
        blank=True,
        max_length=2000,
    )

    kind = models.CharField(
        max_length=8,
        choices=Challenge.Kind.choices,
    )

    polarity = models.CharField(
        max_length=8,
        choices=Challenge.Polarity.choices,
        default=Challenge.Polarity.POSITIVE,
    )

    target_value = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    unit = models.CharField(
        max_length=30,
        blank=True,
    )

    frequency = models.CharField(
        max_length=8,
        choices=Challenge.Frequency.choices,
        default=Challenge.Frequency.DAILY,
    )

    start_date = models.DateField()

    duration_days = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(366),
        ]
    )

    timezone = models.CharField(
        max_length=64,
        default="UTC",
    )

    failure_policy = models.CharField(
        max_length=10,
        choices=FailurePolicy.choices,
        default=FailurePolicy.NONE,
    )

    failure_limit = models.PositiveIntegerField(
        default=3,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(366),
        ],
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    @property
    def end_date(self):
        return self.start_date + timedelta(
            days=self.duration_days - 1
        )

    @property
    def mode(self):
        return Challenge.Mode.STRICT

    class Meta:
        ordering = ["-created_at", "-pk"]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    duration_days__gte=1,
                    duration_days__lte=366,
                ),
                name="valid_group_challenge_duration",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    failure_limit__gte=1,
                    failure_limit__lte=366,
                ),
                name="valid_group_failure_limit",
            ),
        ]

    def __str__(self):
        return self.title


class GroupHabitLog(models.Model):

    challenge = models.ForeignKey(
        GroupChallenge,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    membership = models.ForeignKey(
        GroupMembership,
        on_delete=models.CASCADE,
        related_name="group_habit_logs",
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
                    "membership",
                    "period_start",
                ],
                name="unique_group_habit_log",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        value__isnull=False,
                        performed__isnull=True,
                    )
                    | models.Q(
                        value__isnull=True,
                        performed__isnull=False,
                    )
                ),
                name="valid_group_log_value_type",
            ),
        ]


class GroupWarning(models.Model):

    challenge = models.ForeignKey(
        GroupChallenge,
        on_delete=models.CASCADE,
        related_name="warnings",
    )

    membership = models.ForeignKey(
        GroupMembership,
        on_delete=models.CASCADE,
        related_name="warnings",
    )

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_group_warnings",
    )

    period_start = models.DateField()

    consecutive_failures = models.PositiveIntegerField()

    message = models.CharField(
        max_length=250
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = ["-created_at", "-pk"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "challenge",
                    "membership",
                    "period_start",
                ],
                name="unique_group_warning_period",
            )
        ]

class GroupMessage(models.Model):

    group = models.ForeignKey(
        HabitGroup,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_group_messages",
    )

    text = models.TextField(
        max_length=2000
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = ["-pk"]

        indexes = [
            models.Index(
                fields=["group", "-id"],
                name="group_message_history_idx",
            ),
        ]

    def __str__(self):
        return f"Message {self.pk}"