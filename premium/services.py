from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch

from rest_framework.exceptions import ValidationError

from challenges.models import Challenge, HabitLog
from challenges.progress import calculate_progress
from challenges.schedule import get_local_today, get_period

from .models import Subscription

def calculate_premium_progress(user):

    challenges = Challenge.objects.filter(
        owner=user,
    ).prefetch_related(
        Prefetch(
            "logs",
            queryset=HabitLog.objects.filter(
                success=True
            ),
            to_attr="successful_logs",
        )
    )

    completed = []
    qualifying = []
    best_days = 0

    for challenge in challenges:

        today = get_local_today(challenge)

        successful = {
            log.period_start
            for log in challenge.successful_logs
        }

        progress = calculate_progress(
            challenge,
            successful,
            today,
        )

        cursor = challenge.start_date
        current_days = 0

        while (
            cursor <= challenge.end_date
            and cursor < today
        ):

            start, end = get_period(
                challenge,
                cursor,
            )

            if end >= today:
                break

            if start in successful:

                current_days += (
                    end - start
                ).days + 1

                best_days = max(
                    best_days,
                    current_days,
                )

            else:
                current_days = 0

            if end >= challenge.end_date:
                break

            cursor = end + timedelta(days=1)

        if progress["completed"]:

            completed.append(challenge.pk)

            if challenge.duration_days >= 40:
                qualifying.append(challenge.pk)

    qualifying_id = min(qualifying) if qualifying else None

    additional = sorted(
        pk for pk in completed
        if pk != qualifying_id
    )

    return {
        "required_days": 40,
        "best_successful_days": best_days,
        "days_progress": min(best_days, 40),
        "required_additional_habits": 3,
        "additional_completed_habits": len(additional),
        "qualifying_challenge_id": qualifying_id,
        "completed_challenge_ids": sorted(completed),
        "eligible": (
            qualifying_id is not None
            and len(additional) >= 3
        ),
    }

def get_premium_status(user):

    progress = calculate_premium_progress(user)

    subscription = Subscription.objects.filter(
        user=user
    ).first()

    return {
        **progress,
        "is_premium": subscription is not None,
        "activated_at": (
            subscription.activated_at
            if subscription else None
        ),
    }

@transaction.atomic
def activate_premium(user):

    user = get_user_model().objects.select_for_update().get(
        pk=user.pk
    )

    existing = Subscription.objects.filter(
        user=user
    ).first()

    if existing:
        return existing, False

    progress = calculate_premium_progress(user)

    if not progress["eligible"]:

        raise ValidationError({
            "detail":
                "Premium eligibility requirements have not been met."
        })

    subscription = Subscription.objects.create(
        user=user,
        evidence=progress,
    )

    return subscription, True