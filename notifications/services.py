
from django.db import transaction

from rest_framework.exceptions import (
    ValidationError,
    NotFound,
)

from challenges.models import Challenge

from .models import (
    Reminder,
    NotificationPreference,
)

def lock_challenge(user, challenge_id):

    challenge = (
        Challenge.objects
        .select_for_update()
        .filter(
            pk=challenge_id,
            owner=user,
            archived=False,
        )
        .first()
    )

    if challenge is None:

        raise NotFound(
            "چالش موردنظر یافت نشد."
        )

    return challenge

def validate_reminder_time(
    challenge,
    local_time,
    exclude_id=None,
):

    queryset = Reminder.objects.filter(
        challenge=challenge,
        local_time=local_time,
    )

    if exclude_id is not None:

        queryset = queryset.exclude(
            pk=exclude_id
        )

    if queryset.exists():

        raise ValidationError({
            "local_time":
                "برای این چالش در این ساعت یادآوری وجود دارد."
        })

@transaction.atomic
def create_reminder(*, user, data):

    data = dict(data)

    challenge = lock_challenge(
        user=user,
        challenge_id=data.pop("challenge").pk,
    )

    validate_reminder_time(
        challenge=challenge,
        local_time=data["local_time"],
    )

    return Reminder.objects.create(
        challenge=challenge,
        **data,
    )

@transaction.atomic
def update_reminder(*, user, reminder, data):

    data = dict(data)

    challenge = lock_challenge(
        user=user,
        challenge_id=reminder.challenge_id,
    )

    reminder = (
        Reminder.objects
        .select_for_update()
        .filter(
            pk=reminder.pk,
            challenge=challenge,
        )
        .first()
    )

    if reminder is None:

        raise NotFound(
            "یادآوری موردنظر یافت نشد."
        )

    new_challenge = data.pop(
        "challenge",
        challenge,
    )

    if new_challenge.pk != challenge.pk:

        raise ValidationError({
            "challenge":
                "تغییر چالش یادآوری مجاز نیست."
        })

    local_time = data.get(
        "local_time",
        reminder.local_time,
    )

    validate_reminder_time(
        challenge=challenge,
        local_time=local_time,
        exclude_id=reminder.pk,
    )

    for field, value in data.items():

        setattr(reminder, field, value)

    if data:

        reminder.save(
            update_fields=[
                *data.keys(),
                "updated_at",
            ]
        )

    return reminder

def get_notification_preferences(user):

    preference = (
        NotificationPreference.objects
        .filter(user=user)
        .first()
    )

    if preference is None:

        return NotificationPreference(
            user=user
        )

    return preference

@transaction.atomic
def update_notification_preferences(
    *,
    user,
    data,
):

    preference, _ = (
        NotificationPreference.objects
        .select_for_update()
        .get_or_create(user=user)
    )

    for field, value in data.items():

        setattr(preference, field, value)

    if data:

        preference.save(
            update_fields=[
                *data.keys(),
                "updated_at",
            ]
        )

    return preference