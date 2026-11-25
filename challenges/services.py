
from django.db import transaction

from .models import Challenge


@transaction.atomic
def create_challenge(*, user, data):

    challenge = Challenge.objects.create(
        owner=user,
        timezone=user.timezone,
        **data,
    )

    return challenge


@transaction.atomic
def archive_challenge(*, challenge):

    challenge.archived = True

    challenge.save(
        update_fields=[
            "archived",
            "updated_at",
        ]
    )
