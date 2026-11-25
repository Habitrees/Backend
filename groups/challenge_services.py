
from copy import copy
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.db.models import Prefetch

from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)

from challenges.schedule import (
    get_local_today,
    get_period,
)

from challenges.services import calculate_success
from challenges.streak import calculate_streak
from challenges.progress import calculate_progress

from .models import (
    GroupMembership,
    GroupChallenge,
    GroupHabitLog,
    GroupWarning,
)

from .services import (
    lock_group,
    get_membership,
    remove_group_member,
)


Role = GroupMembership.Role
Policy = GroupChallenge.FailurePolicy


def require_challenge_management(membership):

    if membership.role == Role.OWNER:
        return

    if (
        membership.role == Role.ADMIN
        and membership.can_manage_challenges
    ):
        return

    raise PermissionDenied(
        "مجوز مدیریت چالش گروه را ندارید."
    )


@transaction.atomic
def create_group_challenge(*, user, group_id, data):

    group = lock_group(group_id)

    membership = get_membership(group, user)

    require_challenge_management(membership)

    challenge = GroupChallenge(
        group=group,
        timezone=group.owner.timezone,
        **data,
    )

    try:
        today = get_local_today(challenge)

    except ZoneInfoNotFoundError:
        raise ValidationError({
            "timezone":
                "منطقه زمانی گروه معتبر نیست."
        })

    if challenge.start_date < today:

        raise ValidationError({
            "start_date":
                "تاریخ شروع نمی‌تواند در گذشته باشد."
        })

    challenge.save()

    return challenge


@transaction.atomic
def update_group_challenge(*, user, challenge, data):

    group = lock_group(challenge.group_id)

    membership = get_membership(group, user)

    require_challenge_management(membership)

    challenge = GroupChallenge.objects.get(
        pk=challenge.pk,
        group=group,
    )

    allowed_fields = {
        "title",
        "description",
        "failure_policy",
        "failure_limit",
    }

    changes = {}

    for field, value in data.items():

        if field not in allowed_fields:

            if getattr(challenge, field) != value:

                raise ValidationError({
                    field: "تغییر این فیلد مجاز نیست."
                })

            continue

        changes[field] = value
        setattr(challenge, field, value)

    if changes:

        challenge.save(
            update_fields=[
                *changes.keys(),
                "updated_at",
            ]
        )

    return challenge


def get_member_scope(challenge, membership):

    joined_date = membership.joined_at.astimezone(
        ZoneInfo(challenge.timezone)
    ).date()

    if joined_date > challenge.end_date:
        return None

    first_day = max(
        joined_date,
        challenge.start_date,
    )

    first_period = get_period(
        challenge,
        first_day,
    )

    scoped = copy(challenge)

    scoped.start_date = first_period[0]

    scoped.duration_days = (
        challenge.end_date
        - scoped.start_date
    ).days + 1

    return scoped


@transaction.atomic
def record_group_log(
    *,
    user,
    challenge,
    period_start,
    value=None,
    performed=None,
):

    group = lock_group(challenge.group_id)

    membership = get_membership(group, user)

    challenge = GroupChallenge.objects.get(
        pk=challenge.pk,
        group=group,
    )

    today = get_local_today(challenge)

    period = get_period(challenge, today)

    if period is None:

        raise ValidationError({
            "date": "چالش فعال نیست."
        })

    scoped = get_member_scope(
        challenge,
        membership,
    )

    if scoped is None or today < scoped.start_date:

        raise ValidationError({
            "date": "عضو در این بازه واجد شرایط نیست."
        })

    if period_start != period[0]:

        raise ValidationError({
            "date":
                "فقط ثبت عملکرد بازه جاری مجاز است."
        })

    success = calculate_success(
        challenge,
        value=value,
        performed=performed,
    )

    return GroupHabitLog.objects.update_or_create(
        challenge=challenge,
        membership=membership,
        period_start=period_start,
        defaults={
            "value": value,
            "performed": performed,
            "success": success,
        },
    )


def build_member_progress(
    challenge,
    membership,
    logs,
    today,
):

    scoped = get_member_scope(
        challenge,
        membership,
    )

    successful_periods = [
        log.period_start
        for log in logs
        if log.success
    ]

    if scoped is None:

        progress = {
            "total_periods": 0,
            "successful_periods": 0,
            "progress_percent": 0.0,
        }

        streak = {
            "current_streak": 0,
            "best_streak": 0,
            "consecutive_failures": 0,
        }

    else:

        progress = calculate_progress(
            scoped,
            successful_periods,
            today,
        )

        streak = calculate_streak(
            scoped,
            successful_periods,
            today,
        )

    return {
        "user_id": membership.user_id,
        "username": membership.user.username,
        "full_name": membership.user.full_name,
        "role": membership.role,

        "total_periods": progress["total_periods"],

        "successful_periods":
            progress["successful_periods"],

        "progress_percent":
            progress["progress_percent"],

        "current_streak":
            streak["current_streak"],

        "best_streak":
            streak["best_streak"],

        "consecutive_failures":
            streak["consecutive_failures"],

        "policy_triggered": (
            membership.role == Role.MEMBER
            and challenge.failure_policy != Policy.NONE
            and streak["consecutive_failures"]
                >= challenge.failure_limit
        ),
    }


def get_group_progress(*, user, challenge):

    get_membership(challenge.group, user)

    today = get_local_today(challenge)

    memberships = (
        GroupMembership.objects
        .filter(group=challenge.group)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "group_habit_logs",
                queryset=GroupHabitLog.objects.filter(
                    challenge=challenge,
                ),
                to_attr="challenge_logs",
            )
        )
    )

    return [
        build_member_progress(
            challenge=challenge,
            membership=membership,
            logs=membership.challenge_logs,
            today=today,
        )
        for membership in memberships
    ]


@transaction.atomic
def apply_failure_policy(
    *,
    actor,
    challenge,
    user_id,
):

    group = lock_group(challenge.group_id)

    membership = get_membership(group, actor)

    challenge = GroupChallenge.objects.get(
        pk=challenge.pk,
        group=group,
    )

    policy = challenge.failure_policy

    if membership.role not in (
        Role.OWNER,
        Role.ADMIN,
    ):
        raise PermissionDenied(
            "مجوز اجرای سیاست گروه را ندارید."
        )

    if policy == Policy.NONE:

        raise ValidationError({
            "failure_policy":
                "سیاست شکست فعال نیست."
        })

    if membership.role == Role.ADMIN:

        if (
            policy == Policy.WARN
            and not membership.can_warn_members
        ):
            raise PermissionDenied(
                "مجوز هشدار به اعضا را ندارید."
            )

        if (
            policy == Policy.REMOVE
            and not membership.can_manage_members
        ):
            raise PermissionDenied(
                "مجوز حذف اعضا را ندارید."
            )

    target = (
        GroupMembership.objects
        .filter(
            group=group,
            user_id=user_id,
        )
        .select_related("user")
        .first()
    )

    if target is None:
        raise NotFound("عضو گروه یافت نشد.")

    if target.role != Role.MEMBER:

        raise ValidationError({
            "user_id":
                "این سیاست فقط برای اعضای عادی اجرا می‌شود."
        })

    today = get_local_today(challenge)

    logs = GroupHabitLog.objects.filter(
        challenge=challenge,
        membership=target,
    )

    progress = build_member_progress(
        challenge=challenge,
        membership=target,
        logs=logs,
        today=today,
    )

    if not progress["policy_triggered"]:

        raise ValidationError({
            "detail":
                "تعداد شکست‌های عضو به حد تعیین‌شده نرسیده است."
        })

    if policy == Policy.REMOVE:

        remove_group_member(
            actor=actor,
            group=group,
            user_id=user_id,
        )

        return {
            "action": "remove",
            "user_id": user_id,
            "warning_id": None,
        }

    scoped = get_member_scope(
        challenge,
        target,
    )

    current_period = get_period(
        scoped,
        today,
    )

    if current_period is not None:

        last_closed_day = (
            current_period[0]
            - timedelta(days=1)
        )

    else:
        last_closed_day = scoped.end_date

    last_period = get_period(
        scoped,
        last_closed_day,
    )

    warning, _ = GroupWarning.objects.get_or_create(
        challenge=challenge,
        membership=target,
        period_start=last_period[0],
        defaults={
            "issued_by": actor,
            "consecutive_failures":
                progress["consecutive_failures"],
            "message":
                "تعداد شکست‌های شما به حد تعیین‌شده گروه رسیده است.",
        },
    )

    return {
        "action": "warn",
        "user_id": user_id,
        "warning_id": warning.pk,
    }
