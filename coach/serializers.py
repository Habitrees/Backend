from rest_framework import serializers

from .models import AIConversation, AIMessage, AIProposal


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIConversation
        fields = ("id", "title", "created_at")


class MessageSerializer(serializers.ModelSerializer):
    text = serializers.CharField(max_length=4000)
    proposal_id = serializers.IntegerField(source="proposal.pk", read_only=True, default=None)

    class Meta:
        model = AIMessage
        fields = ("id", "text", "reply_to", "proposal_id", "created_at")
        read_only_fields = ("reply_to",)


class ProposalSerializer(serializers.ModelSerializer):

    class Meta:
        model = AIProposal

        fields = (
            "id",
            "action",
            "challenge",
            "changes",
            "result_challenge",
            "expires_at",
            "decision",
            "decided_at",
        )

        read_only_fields = fields


class ChallengeChanges(serializers.DictField):

    allowed_fields = {
        "title",
        "description",
        "kind",
        "polarity",
        "target_value",
        "unit",
        "frequency",
        "mode",
        "start_date",
        "duration_days",
    }

    def to_internal_value(self, data):

        changes = super().to_internal_value(data)

        if not changes:

            raise serializers.ValidationError(
                "At least one challenge field is required."
            )

        unknown = set(changes) - self.allowed_fields

        if unknown:

            raise serializers.ValidationError(
                "Unsupported challenge fields: "
                + ", ".join(sorted(unknown))
            )

        return changes

class ProposalInput(serializers.Serializer):

    action = serializers.ChoiceField(
        choices=AIProposal.Action.choices,
        default=AIProposal.Action.UPDATE,
    )

    challenge_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
        required=False,
    )

    changes = ChallengeChanges()

    def validate(self, attrs):

        action = attrs["action"]

        if action == AIProposal.Action.UPDATE:

            if "challenge_id" not in attrs:

                raise serializers.ValidationError({
                    "challenge_id":
                        "Required for update proposals."
                })

        elif "challenge_id" in attrs:

            raise serializers.ValidationError({
                "challenge_id":
                    "Not allowed for create proposals."
            })

        return attrs

class CoachResult(serializers.Serializer):
    text = serializers.CharField(max_length=4000)
    proposal = ProposalInput(required=False)
