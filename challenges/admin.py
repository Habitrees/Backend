from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import Challenge


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
