
from datetime import timedelta

from .schedule import get_period


def calculate_progress(
    challenge,
    successful_periods,
    today,
):

    successful_periods = set(successful_periods)

    total = 0
    successful = 0

    cursor = challenge.start_date

    while cursor <= challenge.end_date:

        period_start, period_end = get_period(
            challenge,
            cursor,
        )

        total += 1

        if (
            period_start <= today
            and period_start in successful_periods
        ):
            successful += 1

        if period_end >= challenge.end_date:
            break

        cursor = period_end + timedelta(days=1)

    percentage = (
        round(successful / total * 100, 2)
        if total
        else 0.0
    )

    completed = (
        total > 0
        and successful == total
        and today > challenge.end_date
    )

    return {
        "total_periods": total,
        "successful_periods": successful,
        "progress_percent": percentage,
        "completed": completed,
    }


def get_plant_stage(progress, completed):

    if completed:
        return 5, "mature"

    if progress < 25:
        return 1, "seed"

    if progress < 50:
        return 2, "sprout"

    if progress < 75:
        return 3, "small"

    return 4, "growing"


def build_plant_data(
    challenge,
    successful_periods,
    today,
):

    progress = calculate_progress(
        challenge,
        successful_periods,
        today,
    )

    stage, stage_key = get_plant_stage(
        progress["progress_percent"],
        progress["completed"],
    )

    if progress["completed"]:
        plant_status = "completed"

    elif challenge.archived:
        plant_status = "archived"

    elif today < challenge.start_date:
        plant_status = "upcoming"

    elif today > challenge.end_date:
        plant_status = "ended_unsuccessful"

    else:
        plant_status = "growing"

    return {
        "challenge_id": challenge.pk,
        "challenge_title": challenge.title,
        "stage": stage,
        "stage_key": stage_key,
        "status": plant_status,
        **progress,
    }
