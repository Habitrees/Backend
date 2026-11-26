
import json
import logging

from asgiref.sync import async_to_sync

from channels.generic.websocket import (
    WebsocketConsumer,
)

from rest_framework.exceptions import (
    AuthenticationFailed,
    NotFound,
    ValidationError,
)

from rest_framework_simplejwt.authentication import (
    JWTAuthentication,
)

from .models import GroupMembership

from .chat_services import create_group_message

logger = logging.getLogger(__name__)

class GroupChatConsumer(WebsocketConsumer):

    def connect(self):

        self.group_id = int(
            self.scope["url_route"]["kwargs"]["group_id"]
        )

        self.room_name = (
            f"chat.group.{self.group_id}"
        )

        self.membership_room = None
        self.membership_id = None
        self.user = None
        self.raw_token = None
        self.authorized = False

        self.accept()

        self.send_json({
            "type": "auth_required",
        })

    def send_json(self, data):

        self.send(
            text_data=json.dumps(
                data,
                ensure_ascii=False,
            )
        )

    def reject(self, code, reason):

        self.authorized = False

        self.send_json({
            "type": "error",
            "code": reason,
        })

        self.close(code=code)

    def authenticate(self, data):

        token = data.get("access_token")

        if (
            data.get("type") != "auth"
            or not isinstance(token, str)
            or len(token) > 4096
        ):

            self.reject(4401, "invalid_token")
            return

        authentication = JWTAuthentication()

        try:

            validated_token = (
                authentication.get_validated_token(
                    token
                )
            )

            user = authentication.get_user(
                validated_token
            )

        except AuthenticationFailed:

            self.reject(4401, "invalid_token")
            return

        membership = GroupMembership.objects.filter(
            group_id=self.group_id,
            user=user,
            user__is_active=True,
        ).first()

        if membership is None:

            self.reject(4403, "not_a_member")
            return

        self.user = user
        self.raw_token = token
        self.membership_id = membership.pk

        self.membership_room = (
            f"chat.membership.{membership.pk}"
        )

        self.authorized = True

        async_to_sync(
            self.channel_layer.group_add
        )(
            self.room_name,
            self.channel_name,
        )

        async_to_sync(
            self.channel_layer.group_add
        )(
            self.membership_room,
            self.channel_name,
        )

        if not self.check_access():
            return

        self.send_json({
            "type": "auth_ok",
            "group_id": self.group_id,
            "user_id": user.pk,
        })

    def check_access(self):

        if not self.authorized:
            return False

        authentication = JWTAuthentication()

        try:

            token = authentication.get_validated_token(
                self.raw_token
            )

            authentication.get_user(token)

        except AuthenticationFailed:

            self.reject(4401, "token_expired")
            return False

        exists = GroupMembership.objects.filter(
            pk=self.membership_id,
            group_id=self.group_id,
            user_id=self.user.pk,
            user__is_active=True,
        ).exists()

        if not exists:

            self.reject(4403, "membership_revoked")
            return False

        return True

    def receive(
        self,
        text_data=None,
        bytes_data=None,
    ):

        if (
            text_data is None
            or len(text_data) > 10000
        ):

            self.reject(4400, "invalid_payload")
            return

        try:

            data = json.loads(text_data)

        except (ValueError, TypeError):

            self.send_json({
                "type": "error",
                "code": "invalid_json",
            })

            return

        if not isinstance(data, dict):

            self.send_json({
                "type": "error",
                "code": "invalid_payload",
            })

            return

        if not self.authorized:

            self.authenticate(data)
            return

        if not self.check_access():
            return

        if data.get("type") != "message":

            self.send_json({
                "type": "error",
                "code": "unsupported_event",
            })

            return

        try:

            message = create_group_message(
                user=self.user,
                group_id=self.group_id,
                membership_id=self.membership_id,
                text=data.get("text"),
            )

        except ValidationError:

            self.send_json({
                "type": "error",
                "code": "invalid_message",
            })

            return

        except NotFound:

            self.reject(4403, "membership_revoked")
            return

        try:

            async_to_sync(
                self.channel_layer.group_send
            )(
                self.room_name,
                {
                    "type": "chat.message",
                    "message": message,
                },
            )

        except Exception:

            logger.exception(
                "Chat broadcast failed"
            )

            self.send_json({
                "type": "error",
                "code": "broadcast_failed",
                "message_id": message["id"],
            })

    def chat_message(self, event):

        if not self.check_access():
            return

        self.send_json({
            "type": "message",
            "message": event["message"],
        })

    def membership_revoked(self, event):

        self.reject(4403, "membership_revoked")

    def disconnect(self, close_code):

        self.authorized = False
        self.raw_token = None

        if self.membership_room:

            async_to_sync(
                self.channel_layer.group_discard
            )(
                self.membership_room,
                self.channel_name,
            )

        async_to_sync(
            self.channel_layer.group_discard
        )(
            self.room_name,
            self.channel_name,
        )