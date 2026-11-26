from rest_framework import serializers

from .services import PERIODS
from .models import SmartReport

class ReportDateQuery(serializers.Serializer):
    date = serializers.DateField(required=False)

    def validate_date(self, value):
        if not 1900 <= value.year <= 9998:
            raise serializers.ValidationError("Year must be between 1900 and 9998.")
        return value


class ReportQuery(ReportDateQuery):
    export = serializers.ChoiceField(choices=("csv", "pdf"), required=False)
    language = serializers.ChoiceField(choices=("en", "fa"), required=False)


class MetricsSerializer(serializers.Serializer):
    success_count = serializers.IntegerField()
    failure_count = serializers.IntegerField()
    completion_rate = serializers.FloatField()


class PreviousPeriodSerializer(MetricsSerializer):
    period_start = serializers.DateField()
    period_end = serializers.DateField()


class PerformanceSerializer(MetricsSerializer):
    challenge_id = serializers.IntegerField()
    title = serializers.CharField()
    current_streak = serializers.IntegerField()
    best_streak = serializers.IntegerField()


class ReportSerializer(PreviousPeriodSerializer):
    period = serializers.ChoiceField(choices=PERIODS)
    current_streak = serializers.IntegerField()
    best_streak = serializers.IntegerField()
    previous_period = PreviousPeriodSerializer()
    completion_rate_change = serializers.FloatField()
    challenge_performance = PerformanceSerializer(many=True)
class SmartReportSerializer(serializers.ModelSerializer):

    class Meta:
        model = SmartReport

        fields = (
            "id",
            "period",
            "period_start",
            "narrative",
            "delivery_status",
            "created_at",
        )

        read_only_fields = fields