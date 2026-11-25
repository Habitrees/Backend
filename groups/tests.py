from django.test import TestCase

# Create your tests here.

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase

from .models import GroupMembership


class GroupAPITests(APITestCase):

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
            "+989121234590",
            "group_owner",
        )

        self.member = self.create_user(
            "+989121234591",
            "group_member",
        )

        self.other = self.create_user(
            "+989121234592",
            "other_member",
        )

        self.client.force_authenticate(
            user=self.owner
        )

    def create_group(self, visibility="public"):

        response = self.client.post(
            "/api/groups/",
            {
                "name": "Test Group",
                "visibility": visibility,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        return response.data

    def join_group(self, group, user):

        self.client.force_authenticate(
            user=user
        )

        return self.client.post(
            "/api/groups/join/",
            {"public_id": group["public_id"]},
            format="json",
        )

    def test_create_group_and_owner(self):

        group = self.create_group()

        membership = GroupMembership.objects.get(
            group_id=group["id"],
            user=self.owner,
        )

        self.assertEqual(
            membership.role, "owner"
        )

        self.assertTrue(
            membership.can_manage_members
        )

    def test_public_discovery_and_join(self):

        group = self.create_group()

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.get(
            "/api/groups/discover/",
            {"public_id": group["public_id"]},
        )

        self.assertEqual(
            response.status_code, 200
        )

        response = self.join_group(
            group,
            self.member,
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertEqual(
            response.data["role"], "member"
        )

        # Joining twice must not duplicate membership.
        self.join_group(group, self.member)

        self.assertEqual(
            GroupMembership.objects.filter(
                group_id=group["id"],
                user=self.member,
            ).count(),
            1,
        )

    def test_private_group_hidden(self):

        group = self.create_group("private")

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.get(
            "/api/groups/discover/",
            {"public_id": group["public_id"]},
        )

        self.assertEqual(
            response.status_code, 404
        )

        response = self.join_group(
            group,
            self.member,
        )

        self.assertEqual(
            response.status_code, 404
        )

        response = self.client.get(
            f"/api/groups/{group['id']}/"
        )

        self.assertEqual(
            response.status_code, 404
        )

    def test_owner_can_add_private_member(self):

        group = self.create_group("private")

        response = self.client.post(
            f"/api/groups/{group['id']}/members/",
            {"username": self.member.username},
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.get(
            f"/api/groups/{group['id']}/"
        )

        self.assertEqual(
            response.status_code, 200
        )

    def test_regular_member_cannot_manage_group(self):

        group = self.create_group()

        self.join_group(
            group,
            self.member,
        )

        response = self.client.post(
            f"/api/groups/{group['id']}/members/",
            {"username": self.other.username},
            format="json",
        )

        self.assertEqual(
            response.status_code, 403
        )

        response = self.client.patch(
            f"/api/groups/{group['id']}/",
            {"name": "Unauthorized change"},
            format="json",
        )

        self.assertEqual(
            response.status_code, 403
        )

        response = self.client.patch(
            f"/api/groups/{group['id']}/members/"
            f"{self.member.pk}/",
            {"role": "admin"},
            format="json",
        )

        self.assertEqual(
            response.status_code, 403
        )

    def test_admin_permissions(self):

        group = self.create_group()

        self.join_group(
            group,
            self.member,
        )

        self.client.force_authenticate(
            user=self.owner
        )

        response = self.client.patch(
            f"/api/groups/{group['id']}/members/"
            f"{self.member.pk}/",
            {
                "role": "admin",
                "can_manage_members": True,
                "can_manage_challenges": False,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.post(
            f"/api/groups/{group['id']}/members/",
            {"username": self.other.username},
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        response = self.client.delete(
            f"/api/groups/{group['id']}/members/"
            f"{self.owner.pk}/"
        )

        self.assertEqual(
            response.status_code, 403
        )

    def test_remove_member_revokes_access(self):

        group = self.create_group()

        self.join_group(
            group,
            self.member,
        )

        self.client.force_authenticate(
            user=self.owner
        )

        response = self.client.delete(
            f"/api/groups/{group['id']}/members/"
            f"{self.member.pk}/"
        )

        self.assertEqual(
            response.status_code, 204
        )

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.get(
            f"/api/groups/{group['id']}/members/"
        )

        self.assertEqual(
            response.status_code, 404
        )

    def test_leave_group(self):

        group = self.create_group()

        response = self.client.post(
            f"/api/groups/{group['id']}/leave/"
        )

        self.assertEqual(
            response.status_code, 400
        )

        self.join_group(
            group,
            self.member,
        )

        response = self.client.post(
            f"/api/groups/{group['id']}/leave/"
        )

        self.assertEqual(
            response.status_code, 204
        )

        self.assertFalse(
            GroupMembership.objects.filter(
                group_id=group["id"],
                user=self.member,
            ).exists()
        )

    def test_authentication_required(self):

        self.client.force_authenticate(
            user=None
        )

        response = self.client.get(
            "/api/groups/"
        )

        self.assertEqual(
            response.status_code, 401
        )
