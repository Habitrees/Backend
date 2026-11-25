
from django.db import transaction

from rest_framework.exceptions import (
    ValidationError,
    NotFound,
)

from .models import Challenge, HabitLog

from .schedule import (
    get_local_today,
    get_period,
)

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


def calculate_success(
    challenge,
    value=None,
    performed=None,
):

    if challenge.kind == Challenge.Kind.BINARY:

        if performed is None or value is not None:

            raise ValidationError({
                "performed":
                    "وضعیت انجام فعالیت را مشخص کنید."
            })

        if challenge.polarity == Challenge.Polarity.POSITIVE:
            return performed

        return not performed

    if value is None or performed is not None:

        raise ValidationError({
            "value":
                "مقدار عددی فعالیت را وارد کنید."
        })

    if challenge.target_value is None:

        raise ValidationError({
            "target_value":
                "هدف عددی چالش مشخص نشده است."
        })

    if challenge.polarity == Challenge.Polarity.POSITIVE:

        return value >= challenge.target_value

    return value <= challenge.target_value


@transaction.atomic
def record_habit_log(
    *,
    challenge,
    period_start,
    value=None,
    performed=None,
):

    challenge = (
        Challenge.objects
        .select_for_update()
        .filter(
            pk=challenge.pk,
            owner_id=challenge.owner_id,
            archived=False,
        )
        .first()
    )

    if challenge is None:

        raise NotFound(
            "چالش موردنظر یافت نشد."
        )

    today = get_local_today(challenge)

    period = get_period(
        challenge,
        today,
    )

    if period is None:

        raise ValidationError({
            "date":
                "چالش در حال حاضر فعال نیست."
        })

    current_start, current_end = period

    if period_start != current_start:

        raise ValidationError({
            "date":
                "فقط ثبت عملکرد بازه فعلی مجاز است."
        })

    success = calculate_success(
        challenge,
        value=value,
        performed=performed,
    )

    log, created = HabitLog.objects.update_or_create(

        challenge=challenge,

        period_start=period_start,

        defaults={
            "value": value,
            "performed": performed,
            "success": success,
        },

    )

    return log, created
