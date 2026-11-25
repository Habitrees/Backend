from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import (
    HabitGroup,
    GroupMembership,
)

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