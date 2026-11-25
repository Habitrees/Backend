from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import (
    Reminder,
    NotificationPreference,
)

@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "challenge",
        "local_time",
        "enabled",
    )

    list_filter = (
        "enabled",
        "local_time",
    )

    search_fields = (
        "challenge__title",
        "challenge__owner__username",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "in_app_enabled",
        "push_enabled",
        "email_reports_enabled",
        "telegram_reports_enabled",
    )

    readonly_fields = (
        "updated_at",
    )