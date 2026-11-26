from rest_framework import serializers

from .models import Subscription

class PremiumStatusSerializer(serializers.Serializer):

    is_premium = serializers.BooleanField()
    eligible = serializers.BooleanField()

    required_days = serializers.IntegerField()
    best_successful_days = serializers.IntegerField()
    days_progress = serializers.IntegerField()

    required_additional_habits = serializers.IntegerField()
    additional_completed_habits = serializers.IntegerField()

    qualifying_challenge_id = serializers.IntegerField(
        allow_null=True
    )

    completed_challenge_ids = serializers.ListField(
        child=serializers.IntegerField()
    )

    activated_at = serializers.DateTimeField(
        allow_null=True
    )

class SubscriptionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Subscription

        fields = (
            "id",
            "activated_at",
            "source",
            "evidence",
        )

        read_only_fields = fields