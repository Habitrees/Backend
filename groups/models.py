from django.db import models

# Create your models here.

import uuid

from django.conf import settings
from django.db import models

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