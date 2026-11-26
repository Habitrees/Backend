
from rest_framework import serializers

from .models import (
    HabitGroup,
    GroupMembership,
)
from datetime import timedelta

from .models import (
    GroupChallenge,
    GroupHabitLog,
    GroupWarning,
)
from .models import GroupMessage

class GroupSerializer(serializers.ModelSerializer):

    class Meta:

        model = HabitGroup

        fields = [
            "id",
            "owner",
            "name",
            "description",
            "visibility",
            "public_id",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "owner",
            "public_id",
            "created_at",
            "updated_at",
        ]

class PublicGroupSerializer(serializers.ModelSerializer):

    class Meta:

        model = HabitGroup

        fields = [
            "id",
            "name",
            "description",
            "visibility",
            "public_id",
        ]

        read_only_fields = fields

class GroupMembershipSerializer(
    serializers.ModelSerializer
):

    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    full_name = serializers.CharField(
        source="user.full_name",
        read_only=True,
    )

    class Meta:

        model = GroupMembership

        fields = [
            "id",
            "group",
            "user",
            "username",
            "full_name",
            "role",
            "can_manage_members",
            "can_manage_challenges",
            "can_warn_members",
            "joined_at",
        ]

        read_only_fields = fields

class JoinGroupSerializer(serializers.Serializer):

    public_id = serializers.UUIDField()

class AddMemberSerializer(serializers.Serializer):

    username = serializers.CharField(
        max_length=30
    )

class UpdateMemberSerializer(serializers.Serializer):

    role = serializers.ChoiceField(
        choices=["admin", "member"],
        required=False,
    )

    can_manage_members = serializers.BooleanField(
        required=False
    )

    can_manage_challenges = serializers.BooleanField(
        required=False
    )

    can_warn_members = serializers.BooleanField(
        required=False
    )


class GroupChallengeSerializer(
    serializers.ModelSerializer
):

    end_date = serializers.DateField(
        read_only=True
    )

    mode = serializers.CharField(
        read_only=True
    )

    class Meta:

        model = GroupChallenge

        fields = [
            "id",
            "group",
            "title",
            "description",
            "kind",
            "polarity",
            "target_value",
            "unit",
            "frequency",
            "mode",
            "start_date",
            "end_date",
            "duration_days",
            "timezone",
            "failure_policy",
            "failure_limit",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "group",
            "mode",
            "timezone",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):

        if self.instance is not None:

            immutable_fields = (
                "kind",
                "polarity",
                "target_value",
                "unit",
                "frequency",
                "start_date",
                "duration_days",
            )

            for field in immutable_fields:

                if (
                    field in attrs
                    and attrs[field] != getattr(
                        self.instance, field
                    )
                ):
                    raise serializers.ValidationError({
                        field:
                            "این فیلد پس از ساخت قابل تغییر نیست."
                    })

            return attrs

        kind = attrs["kind"]

        polarity = attrs.get(
            "polarity",
            "positive",
        )

        target = attrs.get("target_value")

        unit = attrs.get("unit", "")

        if kind == "binary":

            if target is not None or unit:

                raise serializers.ValidationError({
                    "target_value":
                        "چالش Binary نباید هدف عددی یا واحد داشته باشد."
                })

        else:

            if target is None:

                raise serializers.ValidationError({
                    "target_value":
                        "هدف عددی الزامی است."
                })

            if polarity == "positive" and target <= 0:

                raise serializers.ValidationError({
                    "target_value":
                        "هدف چالش مثبت باید بیشتر از صفر باشد."
                })

            if kind == "time" and unit != "minutes":

                raise serializers.ValidationError({
                    "unit":
                        "واحد زمان باید minutes باشد."
                })

            if kind == "count" and not unit:

                raise serializers.ValidationError({
                    "unit":
                        "واحد شمارش الزامی است."
                })

        try:

            attrs["start_date"] + timedelta(
                days=attrs["duration_days"] - 1
            )

        except OverflowError:

            raise serializers.ValidationError({
                "start_date":
                    "تاریخ پایان معتبر نیست."
            })

        return attrs


class GroupHabitLogSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = GroupHabitLog

        fields = [
            "id",
            "challenge",
            "membership",
            "period_start",
            "value",
            "performed",
            "success",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class GroupMemberProgressSerializer(
    serializers.Serializer
):

    user_id = serializers.IntegerField()

    username = serializers.CharField()

    full_name = serializers.CharField()

    role = serializers.CharField()

    total_periods = serializers.IntegerField()

    successful_periods = serializers.IntegerField()

    progress_percent = serializers.FloatField()

    current_streak = serializers.IntegerField()

    best_streak = serializers.IntegerField()

    consecutive_failures = serializers.IntegerField()

    policy_triggered = serializers.BooleanField()


class GroupWarningSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = GroupWarning

        fields = [
            "id",
            "challenge",
            "issued_by",
            "period_start",
            "consecutive_failures",
            "message",
            "created_at",
        ]

        read_only_fields = fields


class ApplyPolicySerializer(serializers.Serializer):

    user_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
    )


class PolicyResultSerializer(serializers.Serializer):

    action = serializers.ChoiceField(
        choices=["warn", "remove"]
    )

    user_id = serializers.IntegerField()

    warning_id = serializers.IntegerField(
        allow_null=True
    )


class GroupMessageSerializer(
    serializers.ModelSerializer
):

    username = serializers.CharField(
        source="sender.username",
        read_only=True,
        allow_null=True,
    )

    full_name = serializers.CharField(
        source="sender.full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:

        model = GroupMessage

        fields = [
            "id",
            "group",
            "sender",
            "username",
            "full_name",
            "text",
            "created_at",
        ]

        read_only_fields = fields

class MessageHistoryQuerySerializer(
    serializers.Serializer
):

    before_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
        required=False,
    )

    limit = serializers.IntegerField(
        min_value=1,
        max_value=100,
        default=50,
    )

class MessageHistorySerializer(
    serializers.Serializer
):

    messages = GroupMessageSerializer(
        many=True
    )

    has_more = serializers.BooleanField()

    next_before_id = serializers.IntegerField(
        allow_null=True
    )