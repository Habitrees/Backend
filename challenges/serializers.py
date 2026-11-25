
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework import serializers

from .models import Challenge


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

    def get_status(self, obj):

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
