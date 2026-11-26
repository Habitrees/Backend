from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Subscription

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "source",
        "activated_at",
    )

    readonly_fields = (
        "user",
        "source",
        "activated_at",
        "evidence",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False