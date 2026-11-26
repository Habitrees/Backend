
from asgiref.sync import async_to_sync

from channels.layers import get_channel_layer

from django.db import transaction

def revoke_membership_connections(
    membership_id,
):

    def notify():

        channel_layer = get_channel_layer()

        async_to_sync(
            channel_layer.group_send
        )(
            f"chat.membership.{membership_id}",
            {
                "type": "membership.revoked",
            },
        )

    transaction.on_commit(
        notify,
        robust=True,
    )