from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import Challenge, HabitLog

@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "title",
        "owner",
        "kind",
        "frequency",
        "mode",
        "archived",
    )

    list_filter = (
        "kind",
        "polarity",
        "frequency",
        "mode",
        "archived",
    )

    search_fields = (
        "title",
        "owner__username",
        "owner__phone",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

@admin.register(HabitLog)
class HabitLogAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "challenge",
        "period_start",
        "value",
        "performed",
        "success",
    )

    list_filter = (
        "success",
        "period_start",
    )

    search_fields = (
        "challenge__title",
        "challenge__owner__username",
    )

    readonly_fields = (
        "challenge",
        "period_start",
        "value",
        "performed",
        "success",
        "created_at",
        "updated_at",
        "recovered_at",
    )

    def has_add_permission(self, request):

        return False

    def has_delete_permission(self, request, obj=None):

        return False