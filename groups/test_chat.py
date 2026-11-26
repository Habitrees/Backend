
from asgiref.sync import async_to_sync

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import (
    TransactionTestCase,
    override_settings,
)
from django.utils import timezone

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import (
    RefreshToken,
)

from Backend.asgi import application

from .models import (
    HabitGroup,
    GroupMembership,
    GroupMessage,
)

from .services import remove_group_member


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": (
                "channels.layers.InMemoryChannelLayer"
            ),
        },
    }
)
class GroupChatTests(TransactionTestCase):

    def create_user(self, phone, username):

        return get_user_model().objects.create_user(
            phone=phone,
            username=username,
            full_name=username,
            password="Strong-Test-Password-2026!",
            timezone="UTC",
            terms_version=settings.TERMS_VERSION,
            terms_accepted_at=timezone.now(),
            phone_verified_at=timezone.now(),
        )

    def setUp(self):

        self.owner = self.create_user(
            "+989121234596",
            "chat_owner",
        )

        self.member = self.create_user(
            "+989121234597",
            "chat_member",
        )

        self.other = self.create_user(
            "+989121234598",
            "chat_other",
        )

        self.group = HabitGroup.objects.create(
            owner=self.owner,
            name="Chat Test Group",
            visibility="private",
        )

        GroupMembership.objects.create(
            group=self.group,
            user=self.owner,
            role="owner",
            can_manage_members=True,
            can_manage_challenges=True,
            can_warn_members=True,
        )

        GroupMembership.objects.create(
            group=self.group,
            user=self.member,
            role="member",
        )

        self.owner_token = str(
            RefreshToken.for_user(
                self.owner
            ).access_token
        )

        self.member_token = str(
            RefreshToken.for_user(
                self.member
            ).access_token
        )

        self.other_token = str(
            RefreshToken.for_user(
                self.other
            ).access_token
        )

        self.socket_url = (
            f"/ws/groups/{self.group.pk}/chat/"
        )

        self.history_url = (
            f"/api/groups/{self.group.pk}/messages/"
        )

    def make_socket(self):

        return WebsocketCommunicator(
            application,
            self.socket_url,
            headers=[
                (
                    b"origin",
                    b"http://localhost:8000",
                ),
            ],
        )

    async def authenticate_socket(
        self,
        communicator,
        token,
    ):

        connected, _ = await communicator.connect()

        self.assertTrue(connected)

        response = (
            await communicator.receive_json_from()
        )

        self.assertEqual(
            response["type"],
            "auth_required",
        )

        await communicator.send_json_to({
            "type": "auth",
            "access_token": token,
        })

        return (
            await communicator.receive_json_from()
        )

    def test_realtime_message_and_persistence(self):

        async def scenario():

            socket_a = self.make_socket()
            socket_b = self.make_socket()

            response = (
                await self.authenticate_socket(
                    socket_a,
                    self.owner_token,
                )
            )

            self.assertEqual(
                response["type"],
                "auth_ok",
            )

            response = (
                await self.authenticate_socket(
                    socket_b,
                    self.member_token,
                )
            )

            self.assertEqual(
                response["type"],
                "auth_ok",
            )

            await socket_a.send_json_to({
                "type": "message",
                "text": "Hello group",
            })

            response_a = (
                await socket_a.receive_json_from()
            )

            response_b = (
                await socket_b.receive_json_from()
            )

            self.assertEqual(
                response_a["type"],
                "message",
            )

            self.assertEqual(
                response_a,
                response_b,
            )

            self.assertEqual(
                response_b["message"]["text"],
                "Hello group",
            )

            await socket_a.disconnect()
            await socket_b.disconnect()

        async_to_sync(scenario)()

        self.assertEqual(
            GroupMessage.objects.filter(
                group=self.group,
                text="Hello group",
            ).count(),
            1,
        )

    def test_outsider_cannot_join_chat(self):

        async def scenario():

            socket = self.make_socket()

            response = (
                await self.authenticate_socket(
                    socket,
                    self.other_token,
                )
            )

            self.assertEqual(
                response["code"],
                "not_a_member",
            )

            closed = await socket.receive_output()

            self.assertEqual(
                closed["type"],
                "websocket.close",
            )

            self.assertEqual(
                closed["code"], 4403
            )

            await socket.disconnect()

        async_to_sync(scenario)()

    def test_invalid_token_rejected(self):

        async def scenario():

            socket = self.make_socket()

            response = (
                await self.authenticate_socket(
                    socket,
                    "invalid-jwt-token",
                )
            )

            self.assertEqual(
                response["code"],
                "invalid_token",
            )

            closed = await socket.receive_output()

            self.assertEqual(
                closed["code"], 4401
            )

            await socket.disconnect()

        async_to_sync(scenario)()

    def test_removed_member_disconnected(self):

        async def scenario():

            socket = self.make_socket()

            response = (
                await self.authenticate_socket(
                    socket,
                    self.member_token,
                )
            )

            self.assertEqual(
                response["type"],
                "auth_ok",
            )

            await database_sync_to_async(
                remove_group_member
            )(
                actor=self.owner,
                group=self.group,
                user_id=self.member.pk,
            )

            response = (
                await socket.receive_json_from()
            )

            self.assertEqual(
                response["code"],
                "membership_revoked",
            )

            closed = await socket.receive_output()

            self.assertEqual(
                closed["code"], 4403
            )

            await socket.disconnect()

        async_to_sync(scenario)()

    def test_message_history_and_privacy(self):

        for number in range(3):

            GroupMessage.objects.create(
                group=self.group,
                sender=self.owner,
                text=f"Message {number}",
            )

        client = APIClient()

        client.force_authenticate(
            user=self.member
        )

        response = client.get(
            self.history_url,
            {"limit": 2},
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertTrue(
            response.data["has_more"]
        )

        self.assertEqual(
            len(response.data["messages"]),
            2,
        )

        response = client.get(
            self.history_url,
            {
                "before_id":
                    response.data["next_before_id"],
                "limit": 2,
            },
        )

        self.assertEqual(
            len(response.data["messages"]),
            1,
        )

        client.force_authenticate(
            user=self.other
        )

        response = client.get(
            self.history_url
        )

        self.assertEqual(
            response.status_code, 404
        )
