
import calendar

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Challenge


def get_local_today(challenge):

    return timezone.localdate(
        timezone=ZoneInfo(challenge.timezone)
    )


def get_period(challenge, day):

    if day < challenge.start_date:
        return None

    if day > challenge.end_date:
        return None

    # Daily challenge
    if challenge.frequency == Challenge.Frequency.DAILY:

        period_start = day
        period_end = day

    # Weekly challenge
    elif challenge.frequency == Challenge.Frequency.WEEKLY:

        period_start = day - timedelta(
            days=day.weekday()
        )

        period_end = period_start + timedelta(
            days=6
        )

    # Monthly challenge
    else:

        last_day = calendar.monthrange(
            day.year,
            day.month,
        )[1]

        period_start = day.replace(day=1)

        period_end = day.replace(day=last_day)

    return (
        max(period_start, challenge.start_date),
        min(period_end, challenge.end_date),
    )
