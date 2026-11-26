
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework import serializers

from .models import Challenge, HabitLog, PublicChallenge


class ChallengeSerializer(serializers.ModelSerializer):

    end_date = serializers.DateField(
        read_only=True
    )

    status = serializers.SerializerMethodField()

    class Meta:
        model = Challenge

        fields = [
            "id",
            "title",
            "description",
            "polarity",
            "kind",
            "target_value",
            "unit",
            "start_date",
            "end_date",
            "duration_days",
            "frequency",
            "mode",
            "timezone",
            "status",
            "archived",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "timezone",
            "status",
            "archived",
            "created_at",
            "updated_at",
        ]

    def get_status(self, obj) -> str:

        if obj.archived:
            return "archived"

        today = timezone.localdate(
            timezone=ZoneInfo(obj.timezone)
        )

        if today < obj.start_date:
            return "upcoming"

        if today > obj.end_date:
            return "ended"

        return "active"

    def validate(self, attrs):

        instance = self.instance

        def get_value(field, default=None):
            if field in attrs:
                return attrs[field]

            if instance is not None:
                return getattr(instance, field)

            return default

        kind = get_value("kind")

        polarity = get_value(
            "polarity",
            Challenge.Polarity.POSITIVE,
        )

        target = get_value("target_value")
        unit = get_value("unit", "")

        mode = get_value(
            "mode",
            Challenge.Mode.STRICT,
        )

        frequency = get_value(
            "frequency",
            Challenge.Frequency.DAILY,
        )

        start_date = get_value("start_date")
        duration = get_value("duration_days")

        # Binary challenges do not need a numeric target.
        if kind == Challenge.Kind.BINARY:

            if target is not None:
                raise serializers.ValidationError({
                    "target_value":
                        "چالش Binary نباید هدف عددی داشته باشد."
                })

            if unit:
                raise serializers.ValidationError({
                    "unit":
                        "چالش Binary نباید واحد اندازه‌گیری داشته باشد."
                })

        else:

            if target is None or target < 0:
                raise serializers.ValidationError({
                    "target_value":
                        "مقدار هدف معتبر وارد کنید."
                })

            if (
                polarity == Challenge.Polarity.POSITIVE
                and target == 0
            ):
                raise serializers.ValidationError({
                    "target_value":
                        "هدف عادت مثبت باید بزرگ‌تر از صفر باشد."
                })

            if kind == Challenge.Kind.TIME:

                if unit != "minutes":
                    raise serializers.ValidationError({
                        "unit":
                            "واحد چالش زمانی باید minutes باشد."
                    })

            elif not unit:
                raise serializers.ValidationError({
                    "unit":
                        "واحد اندازه‌گیری را مشخص کنید."
                })

        # Flexible mode currently supports daily challenges.
        if (
            mode == Challenge.Mode.FLEXIBLE
            and frequency != Challenge.Frequency.DAILY
        ):
            raise serializers.ValidationError({
                "mode":
                    "حالت Flexible فعلاً فقط برای چالش روزانه مجاز است."
            })

        if start_date and duration:
            try:
                start_date + timedelta(days=duration - 1)
            except OverflowError:
                raise serializers.ValidationError({
                    "start_date":
                        "بازه تاریخی معتبر نیست."
                })

        if instance is None:

            user_timezone = self.context["request"].user.timezone

            try:
                user_zone = ZoneInfo(user_timezone)

            except (ZoneInfoNotFoundError, ValueError):
                raise serializers.ValidationError({
                    "timezone":
                        "منطقه زمانی پروفایل معتبر نیست."
                })

            today = timezone.localdate(
                timezone=user_zone
            )

            if start_date and start_date < today:
                raise serializers.ValidationError({
                    "start_date":
                        "تاریخ شروع نمی‌تواند در گذشته باشد."
                })

        else:

            today = timezone.localdate(
                timezone=ZoneInfo(instance.timezone)
            )

            protected_fields = [
                "kind",
                "polarity",
                "target_value",
                "unit",
                "start_date",
                "duration_days",
                "frequency",
                "mode",
            ]

            if today >= instance.start_date:

                for field in protected_fields:

                    if (
                        field in attrs
                        and attrs[field] != getattr(instance, field)
                    ):
                        raise serializers.ValidationError({
                            field:
                                "پس از شروع چالش، تغییر این فیلد مجاز نیست."
                        })

            elif start_date and start_date < today:

                raise serializers.ValidationError({
                    "start_date":
                        "تاریخ شروع نمی‌تواند در گذشته باشد."
                })

        return attrs


class PublicChallengeSerializer(serializers.ModelSerializer):

    class Meta:
        model = PublicChallenge

        fields = [
            "id",
            "title",
            "description",
            "category",
            "difficulty",
            "kind",
            "polarity",
            "target_value",
            "unit",
            "duration_days",
            "frequency",
            "mode",
            "published",
            "popularity",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "popularity",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):

        instance = self.instance

        def get_value(field, default=None):
            if field in attrs:
                return attrs[field]

            if instance is not None:
                return getattr(instance, field)

            return default

        kind = get_value("kind")

        polarity = get_value(
            "polarity",
            Challenge.Polarity.POSITIVE,
        )

        target = get_value("target_value")
        unit = get_value("unit", "")

        mode = get_value(
            "mode",
            Challenge.Mode.STRICT,
        )

        frequency = get_value(
            "frequency",
            Challenge.Frequency.DAILY,
        )

        # Binary validation
        if kind == Challenge.Kind.BINARY:

            if target is not None:
                raise serializers.ValidationError({
                    "target_value":
                        "Binary challenges cannot have a numeric target."
                })

            if unit:
                raise serializers.ValidationError({
                    "unit":
                        "Binary challenges cannot have a measurement unit."
                })

        else:

            if target is None:
                raise serializers.ValidationError({
                    "target_value":
                        "A numeric target is required."
                })

            if (
                polarity == Challenge.Polarity.POSITIVE
                and target == 0
            ):
                raise serializers.ValidationError({
                    "target_value":
                        "Target must be greater than zero."
                })

            if kind == Challenge.Kind.TIME:

                if unit != "minutes":
                    raise serializers.ValidationError({
                        "unit":
                            "Time challenges must use minutes."
                    })

            elif not unit:
                raise serializers.ValidationError({
                    "unit":
                        "A measurement unit is required."
                })

        # Flexible mode validation
        if (
            mode == Challenge.Mode.FLEXIBLE
            and frequency != Challenge.Frequency.DAILY
        ):
            raise serializers.ValidationError({
                "mode":
                    "Flexible mode is only available for daily challenges."
            })

        return attrs

class PublicChallengeFilterSerializer(serializers.Serializer):

    category = serializers.SlugField(
        required=False
    )

    difficulty = serializers.ChoiceField(
        choices=PublicChallenge.Difficulty.choices,
        required=False,
    )

    duration_days = serializers.IntegerField(
        min_value=1,
        max_value=366,
        required=False,
    )

    min_duration_days = serializers.IntegerField(
        min_value=1,
        max_value=366,
        required=False,
    )

    max_duration_days = serializers.IntegerField(
        min_value=1,
        max_value=366,
        required=False,
    )

    ordering = serializers.ChoiceField(
        choices=[
            "popular",
            "newest",
            "duration_asc",
            "duration_desc",
        ],
        default="popular",
    )

class HabitLogInputSerializer(serializers.Serializer):

    value = serializers.IntegerField(
        min_value=0,
        max_value=2147483647,
        required=False,
        allow_null=True,
    )

    performed = serializers.BooleanField(
        required=False,
        allow_null=True,
    )


class HabitLogSerializer(serializers.ModelSerializer):

    class Meta:

        model = HabitLog

        fields = [
            "id",
            "challenge",
            "period_start",
            "value",
            "performed",
            "success",
            "recovered_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class ScheduleSerializer(serializers.Serializer):

    frequency = serializers.CharField()

    today = serializers.DateField()

    start_date = serializers.DateField()

    end_date = serializers.DateField()

    current_period_start = serializers.DateField(
        allow_null=True
    )

    current_period_end = serializers.DateField(
        allow_null=True
    )

class StreakSerializer(serializers.Serializer):

    current_streak = serializers.IntegerField()

    best_streak = serializers.IntegerField()

    consecutive_failures = serializers.IntegerField()

    current_period_success = serializers.BooleanField()

    recovery_pending = serializers.BooleanField()

    recoverable_date = serializers.DateField(
        allow_null=True
    )

    can_recover = serializers.BooleanField()

class PlantSerializer(serializers.Serializer):

    challenge_id = serializers.IntegerField()

    challenge_title = serializers.CharField()

    stage = serializers.IntegerField(
        min_value=1,
        max_value=5,
    )

    stage_key = serializers.ChoiceField(
        choices=[
            "seed",
            "sprout",
            "small",
            "growing",
            "mature",
        ]
    )

    status = serializers.ChoiceField(
        choices=[
            "upcoming",
            "growing",
            "completed",
            "ended_unsuccessful",
            "archived",
        ]
    )

    total_periods = serializers.IntegerField()

    successful_periods = serializers.IntegerField()

    progress_percent = serializers.FloatField()

    completed = serializers.BooleanField()

class GardenSerializer(serializers.Serializer):

    total_growing = serializers.IntegerField()

    total_completed = serializers.IntegerField()

    growing = PlantSerializer(many=True)

    completed = PlantSerializer(many=True)

class DashboardUserSerializer(serializers.Serializer):

    id = serializers.IntegerField()

    username = serializers.CharField()

    full_name = serializers.CharField()

class DashboardSummarySerializer(serializers.Serializer):

    total_active = serializers.IntegerField()

    successful_current = serializers.IntegerField()

    failed_current = serializers.IntegerField()

    pending_current = serializers.IntegerField()

    total_growing = serializers.IntegerField()

    total_completed = serializers.IntegerField()

class DashboardChallengeSerializer(serializers.Serializer):

    id = serializers.IntegerField()

    title = serializers.CharField()

    description = serializers.CharField()

    kind = serializers.CharField()

    polarity = serializers.CharField()

    frequency = serializers.CharField()

    mode = serializers.CharField()

    target_value = serializers.IntegerField(
        allow_null=True
    )

    unit = serializers.CharField()

    today = serializers.DateField()

    current_period_start = serializers.DateField()

    current_period_end = serializers.DateField()

    current_status = serializers.ChoiceField(
        choices=[
            "pending",
            "success",
            "failure",
        ]
    )

    current_log = HabitLogSerializer(
        allow_null=True
    )

    success_rate_percent = serializers.FloatField()

    streak = StreakSerializer()

    plant = PlantSerializer()

class DashboardWeeklySerializer(serializers.Serializer):

    total_periods = serializers.IntegerField()

    successful_periods = serializers.IntegerField()

    failed_periods = serializers.IntegerField()

    success_rate_percent = serializers.FloatField()

class DashboardGroupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    visibility = serializers.CharField()


class DashboardSerializer(serializers.Serializer):

    user = DashboardUserSerializer()

    summary = DashboardSummarySerializer()

    active_challenges = DashboardChallengeSerializer(
        many=True
    )

    weekly_summary = DashboardWeeklySerializer()
    monthly_summary = DashboardWeeklySerializer()
    active_groups = DashboardGroupSerializer(many=True)
    recommended_challenges = PublicChallengeSerializer(many=True)

    motivational_message = serializers.CharField()