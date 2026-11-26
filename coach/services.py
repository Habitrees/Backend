from types import SimpleNamespace

from rest_framework.exceptions import ValidationError

from challenges.models import Challenge
from challenges.serializers import ChallengeSerializer

from .models import AIProposal

def validate_proposal(*, user, proposal, lock=False):

    action = proposal["action"]
    changes = proposal["changes"]

    challenge = None

    if action == AIProposal.Action.UPDATE:

        queryset = Challenge.objects.filter(
            pk=proposal.get("challenge_id"),
            owner=user,
            archived=False,
        )

        if lock:
            queryset = queryset.select_for_update()

        challenge = queryset.first()

        if challenge is None:

            raise ValidationError({
                "proposal":
                    "Challenge is unavailable."
            })

    elif action != AIProposal.Action.CREATE:

        raise ValidationError({
            "action": "Unsupported proposal action."
        })

    serializer = ChallengeSerializer(
        instance=challenge,
        data=changes,
        partial=(
            action == AIProposal.Action.UPDATE
        ),
        context={
            "request": SimpleNamespace(user=user)
        },
    )

    serializer.is_valid(
        raise_exception=True
    )

    return challenge, serializer