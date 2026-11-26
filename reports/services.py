from calendar import monthrange
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.utils import timezone

from challenges.models import Challenge, HabitLog
from challenges.schedule import get_local_today, get_period
from challenges.services import calculate_success_rate
from challenges.streak import calculate_streak

PERIODS = ("weekly", "monthly", "yearly")
DAY = timedelta(days=1)


def bounds(period, day):
    if period == "weekly":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        return day.replace(day=1), day.replace(day=monthrange(day.year, day.month)[1])
    return day.replace(month=1, day=1), day.replace(month=12, day=31)


def metrics(success, failure):
    return {
        "success_count": success,
        "failure_count": failure,
        "completion_rate": calculate_success_rate(success, success + failure),
    }


def build_report(user, period, day=None):
    today = timezone.localdate(timezone=ZoneInfo(user.timezone))
    start, end = bounds(period, day or today)
    previous_start, previous_end = bounds(period, start - DAY)
    challenges = Challenge.objects.filter(
        owner=user, start_date__lte=min(today + DAY, end),
    ).order_by("pk").prefetch_related(
        Prefetch("logs", HabitLog.objects.only("challenge_id", "period_start", "success"))
    )
    performance = []
    current_success = current_failure = previous_success = previous_failure = 0
    for challenge in challenges:
        if challenge.end_date < previous_start:
            continue
        actual_today = get_local_today(challenge)
        cutoff = min(end, actual_today)
        logs = {log.period_start: log.success for log in challenge.logs.all()}
        success = failure = 0
        cursor = max(previous_start, challenge.start_date)
        while cursor <= min(cutoff, challenge.end_date):
            period_start, period_end = get_period(challenge, cursor)
            cursor = period_end + DAY
            if period_end > end:
                break
            logged = period_start in logs
            if period_end >= actual_today and not logged:
                continue
            if period_end < start:
                previous_success += int(logs.get(period_start, False))
                previous_failure += int(not logs.get(period_start, False))
            else:
                success += int(logs.get(period_start, False))
                failure += int(not logs.get(period_start, False))

        if challenge.end_date < start or challenge.start_date > cutoff:
            continue
        streak = calculate_streak(
            challenge, {date for date, passed in logs.items() if passed and date <= end},
            min(actual_today, end + DAY) if end < actual_today else actual_today,
        )
        performance.append({
            "challenge_id": challenge.pk,
            "title": challenge.title,
            **metrics(success, failure),
            "current_streak": streak["current_streak"],
            "best_streak": streak["best_streak"],
        })
        current_success += success
        current_failure += failure

    current = metrics(current_success, current_failure)
    previous = metrics(previous_success, previous_failure)
    return {
        "period": period, "period_start": start, "period_end": end,
        **current,
        "current_streak": max((row["current_streak"] for row in performance), default=0),
        "best_streak": max((row["best_streak"] for row in performance), default=0),
        "previous_period": {"period_start": previous_start, "period_end": previous_end, **previous},
        "completion_rate_change": round(current["completion_rate"] - previous["completion_rate"], 2),
        "challenge_performance": performance,
    }
