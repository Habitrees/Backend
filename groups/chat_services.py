
from django.db import transaction

from rest_framework.exceptions import (
    NotFound,
    ValidationError,
)

from .models import (
    GroupMembership,
    GroupMessage,
)

from .services import (
    lock_group,
    get_membership,
)

from .serializers import GroupMessageSerializer


def get_message_history(
    *,
    user,
    group,
    before_id=None,
    limit=50,
):

    get_membership(group, user)

    queryset = GroupMessage.objects.filter(
        group=group,
    ).select_related(
        "sender"
    ).order_by("-pk")

    if before_id is not None:

        queryset = queryset.filter(
            pk__lt=before_id
        )

    rows = list(
        queryset[:limit + 1]
    )

    has_more = len(rows) > limit

    messages = rows[:limit]

    next_before_id = (
        messages[-1].pk
        if has_more and messages
        else None
    )

    return {
        "messages": list(reversed(messages)),
        "has_more": has_more,
        "next_before_id": next_before_id,
    }


@transaction.atomic
def create_group_message(
    *,
    user,
    group_id,
    membership_id,
    text,
):

    group = lock_group(group_id)

    membership = (
        GroupMembership.objects.filter(
            pk=membership_id,
            group=group,
            user=user,
            user__is_active=True,
        ).first()
    )

    if membership is None:
        raise NotFound(
            "دسترسی به گروه وجود ندارد."
        )

    if not isinstance(text, str):

        raise ValidationError({
            "text": "پیام باید متنی باشد."
        })

    text = text.strip()

    if not text or len(text) > 2000 or "\x00" in text:

        raise ValidationError({
            "text":
                "متن پیام باید بین ۱ تا ۲۰۰۰ کاراکتر معتبر باشد."
        })

    message = GroupMessage.objects.create(
        group=group,
        sender=user,
        text=text,
    )

    return dict(
        GroupMessageSerializer(message).data
    )
