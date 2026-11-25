
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
from datetime import timedelta
from django.utils import timezone

from .streak import calculate_streak

from django.db.models import Prefetch
from .progress import build_plant_data

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
    if not success and challenge.mode == Challenge.Mode.FLEXIBLE:

        yesterday = today - timedelta(days=1)

        recovered_yesterday = HabitLog.objects.filter(
            challenge=challenge,
            period_start=yesterday,
            recovered_at__isnull=False,
        ).exists()

        if recovered_yesterday:

            raise ValidationError({
                "detail":
                    "پس از جبران روز گذشته، عملکرد امروز نمی‌تواند ناموفق شود."
            })
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

def get_streak_data(challenge):

    today = get_local_today(challenge)

    successful_periods = HabitLog.objects.filter(
        challenge=challenge,
        success=True,
    ).values_list(
        "period_start",
        flat=True,
    )

    return calculate_streak(
        challenge=challenge,
        successful_periods=successful_periods,
        today=today,
    )

@transaction.atomic
def recover_habit_log(
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

    if (
        challenge.mode != Challenge.Mode.FLEXIBLE
        or challenge.frequency != Challenge.Frequency.DAILY
    ):

        raise ValidationError({
            "mode":
                "جبران فقط برای چالش روزانه Flexible مجاز است."
        })

    today = get_local_today(challenge)

    yesterday = today - timedelta(days=1)

    if not (
        challenge.start_date <= today <= challenge.end_date
    ):

        raise ValidationError({
            "date":
                "چالش فعال نیست."
        })

    if (
        period_start != yesterday
        or yesterday < challenge.start_date
    ):

        raise ValidationError({
            "date":
                "فقط جبران عملکرد روز گذشته مجاز است."
        })

    if HabitLog.objects.filter(
        challenge=challenge,
        period_start=yesterday,
        success=True,
    ).exists():

        raise ValidationError({
            "date":
                "عملکرد روز گذشته قبلاً موفق ثبت شده است."
        })

    today_success = HabitLog.objects.filter(
        challenge=challenge,
        period_start=today,
        success=True,
    ).exists()

    if not today_success:

        raise ValidationError({
            "detail":
                "ابتدا باید هدف امروز را با موفقیت انجام دهید."
        })

    success = calculate_success(
        challenge,
        value=value,
        performed=performed,
    )

    if not success:

        raise ValidationError({
            "detail":
                "عملکرد جبرانی باید به هدف تعیین‌شده برسد."
        })

    log, created = HabitLog.objects.update_or_create(
        challenge=challenge,
        period_start=yesterday,
        defaults={
            "value": value,
            "performed": performed,
            "success": True,
            "recovered_at": timezone.now(),
        },
    )

    return log


def get_plant_data(challenge):

    successful_periods = HabitLog.objects.filter(
        challenge=challenge,
        success=True,
    ).values_list(
        "period_start",
        flat=True,
    )

    return build_plant_data(
        challenge=challenge,
        successful_periods=successful_periods,
        today=get_local_today(challenge),
    )

def get_garden_data(user):

    challenges = Challenge.objects.filter(
        owner=user,
    ).prefetch_related(
        Prefetch(
            "logs",
            queryset=HabitLog.objects.filter(
                success=True,
            ).only(
                "challenge_id",
                "period_start",
            ),
            to_attr="successful_logs",
        )
    )

    growing = []
    completed = []

    for challenge in challenges:

        plant = build_plant_data(
            challenge=challenge,
            successful_periods=[
                log.period_start
                for log in challenge.successful_logs
            ],
            today=get_local_today(challenge),
        )

        if plant["completed"]:

            completed.append(plant)

        elif plant["status"] == "growing":

            growing.append(plant)

    return {
        "total_growing": len(growing),
        "total_completed": len(completed),
        "growing": growing,
        "completed": completed,
    }
