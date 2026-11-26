
from django.contrib.auth import get_user_model
from django.db import transaction

from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)

from .models import (
    HabitGroup,
    GroupMembership,
)
from .chat_events import (
    revoke_membership_connections,
)

Role = GroupMembership.Role

PERMISSION_FIELDS = (
    "can_manage_members",
    "can_manage_challenges",
    "can_warn_members",
)

def lock_group(group_id):

    group = (
        HabitGroup.objects
        .select_for_update()
        .filter(pk=group_id)
        .first()
    )

    if group is None:
        raise NotFound("گروه یافت نشد.")

    return group

def get_membership(group, user):

    membership = GroupMembership.objects.filter(
        group=group,
        user=user,
    ).first()

    if membership is None:
        raise NotFound("گروه یافت نشد.")

    return membership

def require_owner(membership):

    if membership.role != Role.OWNER:
        raise PermissionDenied(
            "فقط مالک گروه اجازه این عملیات را دارد."
        )

def require_member_management(membership):

    if membership.role == Role.OWNER:
        return

    if (
        membership.role == Role.ADMIN
        and membership.can_manage_members
    ):
        return

    raise PermissionDenied(
        "مجوز مدیریت اعضا را ندارید."
    )

@transaction.atomic
def create_group(*, user, data):

    group = HabitGroup.objects.create(
        owner=user,
        **data,
    )

    GroupMembership.objects.create(
        group=group,
        user=user,
        role=Role.OWNER,
        can_manage_members=True,
        can_manage_challenges=True,
        can_warn_members=True,
    )

    return group

@transaction.atomic
def update_group(*, user, group, data):

    group = lock_group(group.pk)

    membership = get_membership(group, user)

    require_owner(membership)

    for field, value in data.items():
        setattr(group, field, value)

    if data:
        group.save(
            update_fields=[
                *data.keys(),
                "updated_at",
            ]
        )

    return group

@transaction.atomic
def join_public_group(*, user, public_id):

    group = (
        HabitGroup.objects
        .select_for_update()
        .filter(
            public_id=public_id,
            visibility=HabitGroup.Visibility.PUBLIC,
        )
        .first()
    )

    if group is None:
        raise NotFound("گروه عمومی یافت نشد.")

    membership, _ = (
        GroupMembership.objects.get_or_create(
            group=group,
            user=user,
        )
    )

    return membership

@transaction.atomic
def add_group_member(*, actor, group, username):

    group = lock_group(group.pk)

    membership = get_membership(group, actor)

    require_member_management(membership)

    user = get_user_model().objects.filter(
        username=username,
        is_active=True,
    ).first()

    if user is None:
        raise NotFound("کاربر یافت نشد.")

    member, created = (
        GroupMembership.objects.get_or_create(
            group=group,
            user=user,
        )
    )

    if not created:
        raise ValidationError({
            "username":
                "این کاربر قبلاً عضو گروه است."
        })

    return member

@transaction.atomic
def update_group_member(
    *,
    actor,
    group,
    user_id,
    data,
):

    group = lock_group(group.pk)

    membership = get_membership(group, actor)

    require_owner(membership)

    target = GroupMembership.objects.filter(
        group=group,
        user_id=user_id,
    ).first()

    if target is None:
        raise NotFound("عضو گروه یافت نشد.")

    if target.role == Role.OWNER:
        raise ValidationError({
            "role":
                "نقش مالک گروه قابل تغییر نیست."
        })

    new_role = data.get("role", target.role)

    if new_role == Role.MEMBER:

        if any(
            data.get(field, False)
            for field in PERMISSION_FIELDS
        ):
            raise ValidationError({
                "role":
                    "عضو عادی نمی‌تواند مجوز مدیریتی داشته باشد."
            })

        for field in PERMISSION_FIELDS:
            setattr(target, field, False)

    else:

        for field in PERMISSION_FIELDS:

            if field in data:
                setattr(
                    target,
                    field,
                    data[field],
                )

    target.role = new_role

    target.save(
        update_fields=[
            "role",
            *PERMISSION_FIELDS,
        ]
    )

    return target

@transaction.atomic
def remove_group_member(*, actor, group, user_id):

    group = lock_group(group.pk)

    membership = get_membership(group, actor)

    require_member_management(membership)

    target = GroupMembership.objects.filter(
        group=group,
        user_id=user_id,
    ).first()

    if target is None:
        raise NotFound("عضو گروه یافت نشد.")

    if target.role == Role.OWNER:
        raise PermissionDenied(
            "حذف مالک گروه مجاز نیست."
        )

    if target.user_id == actor.pk:
        raise ValidationError({
            "detail":
                "برای خروج از API خروج استفاده کنید."
        })

    if (
        target.role == Role.ADMIN
        and membership.role != Role.OWNER
    ):
        raise PermissionDenied(
            "فقط مالک می‌تواند مدیر گروه را حذف کند."
        )

    membership_id = target.pk

    target.delete()

    revoke_membership_connections(
        membership_id
    )

@transaction.atomic
def leave_group(*, user, group):

    group = lock_group(group.pk)

    membership = get_membership(group, user)

    if membership.role == Role.OWNER:
        raise ValidationError({
            "detail":
                "مالک گروه نمی‌تواند از گروه خارج شود."
        })

    membership_id = membership.pk

    membership.delete()

    revoke_membership_connections(
        membership_id
    )