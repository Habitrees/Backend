
from rest_framework import serializers

from challenges.models import Challenge

from .models import (
    Reminder,
    NotificationPreference,
)

class ReminderSerializer(serializers.ModelSerializer):

    timezone = serializers.CharField(
        source="challenge.timezone",
        read_only=True,
    )

    class Meta:

        model = Reminder

        fields = [
            "id",
            "challenge",
            "local_time",
            "timezone",
            "message",
            "enabled",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "timezone",
            "created_at",
            "updated_at",
        ]

        # Duplicate validation is handled by the service.
        validators = []

    def get_fields(self):

        fields = super().get_fields()

        request = self.context.get("request")

        queryset = Challenge.objects.none()

        if (
            request
            and request.user.is_authenticated
        ):

            queryset = Challenge.objects.filter(
                owner=request.user,
                archived=False,
            )

        fields["challenge"].queryset = queryset

        return fields

    def validate_challenge(self, value):

        if (
            self.instance is not None
            and value.pk != self.instance.challenge_id
        ):

            raise serializers.ValidationError(
                "تغییر چالش یادآوری مجاز نیست."
            )

        return value

class NotificationPreferenceSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = NotificationPreference

        fields = [
            "in_app_enabled",
            "push_enabled",
            "email_reports_enabled",
            "telegram_reports_enabled",
            "smart_reports_enabled",
        ]