
from rest_framework import serializers

from .models import (
    HabitGroup,
    GroupMembership,
)

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