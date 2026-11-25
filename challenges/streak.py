
from datetime import timedelta

from .models import Challenge
from .schedule import get_period

def calculate_streak(
    challenge,
    successful_periods,
    today,
):
    successful_periods = set(successful_periods)

    current = 0
    best = 0
    consecutive_failures = 0

    run_before_last_failure = 0
    last_closed_start = None

    current_period_success = False
    recoverable_date = None

    cursor = challenge.start_date

    while (
        cursor <= challenge.end_date
        and cursor <= today
    ):
        period_start, period_end = get_period(
            challenge,
            cursor,
        )

        success = period_start in successful_periods

        # The current period is not closed yet.
        if period_end >= today:

            current_period_success = success

            if success:
                current += 1
                best = max(best, current)

            break

        # Evaluate closed periods.
        last_closed_start = period_start

        if success:

            current += 1
            best = max(best, current)

            consecutive_failures = 0

        else:

            run_before_last_failure = current

            current = 0
            consecutive_failures += 1

        if period_end >= challenge.end_date:
            break

        cursor = period_end + timedelta(days=1)

    # Flexible mode: yesterday may still be recovered.
    if (
        challenge.mode == Challenge.Mode.FLEXIBLE
        and challenge.frequency == Challenge.Frequency.DAILY
        and challenge.start_date <= today <= challenge.end_date
    ):

        yesterday = today - timedelta(days=1)

        if (
            last_closed_start == yesterday
            and yesterday not in successful_periods
        ):

            recoverable_date = yesterday

            # Preserve the previous run temporarily.
            current = max(
                current,
                run_before_last_failure,
            )

    return {
        "current_streak": current,
        "best_streak": best,
        "consecutive_failures": consecutive_failures,
        "current_period_success": current_period_success,
        "recovery_pending": recoverable_date is not None,
        "recoverable_date": recoverable_date,
        "can_recover": (
            recoverable_date is not None
            and current_period_success
        ),
    }