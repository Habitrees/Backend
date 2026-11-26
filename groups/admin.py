from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import (
    HabitGroup,
    GroupMembership,
)

from .models import (
    GroupChallenge,
    GroupHabitLog,
    GroupWarning,
)
from .models import GroupMessage
class ReadOnlyAdmin(admin.ModelAdmin):

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(HabitGroup)
class HabitGroupAdmin(ReadOnlyAdmin):

    list_display = (
        "id",
        "name",
        "owner",
        "visibility",
        "public_id",
        "created_at",
    )

    list_filter = ("visibility",)

    search_fields = (
        "name",
        "owner__username",
    )

@admin.register(GroupMembership)
class GroupMembershipAdmin(ReadOnlyAdmin):

    list_display = (
        "id",
        "group",
        "user",
        "role",
        "can_manage_members",
        "can_manage_challenges",
        "can_warn_members",
    )

    list_filter = ("role",)

    search_fields = (
        "group__name",
        "user__username",
    )


@admin.register(GroupChallenge)
class GroupChallengeAdmin(ReadOnlyAdmin):

    list_display = (
        "id",
        "group",
        "title",
        "frequency",
        "failure_policy",
        "failure_limit",
    )

    list_filter = (
        "frequency",
        "failure_policy",
    )

    search_fields = (
        "title",
        "group__name",
    )

@admin.register(GroupHabitLog)
class GroupHabitLogAdmin(ReadOnlyAdmin):

    list_display = (
        "challenge",
        "membership",
        "period_start",
        "success",
    )

    list_filter = ("success",)

@admin.register(GroupWarning)
class GroupWarningAdmin(ReadOnlyAdmin):

    list_display = (
        "challenge",
        "membership",
        "consecutive_failures",
        "created_at",
    )

@admin.register(GroupMessage)
class GroupMessageAdmin(ReadOnlyAdmin):

    list_display = (
        "id",
        "group",
        "sender",
        "created_at",
    )

    list_filter = ("created_at",)

    search_fields = (
        "group__name",
        "sender__username",
    )