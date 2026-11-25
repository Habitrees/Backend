
from datetime import (
    date,
    datetime,
    timedelta,
    timezone as dt_timezone,
)

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase

from .models import (
    HabitGroup,
    GroupMembership,
    GroupChallenge,
    GroupHabitLog,
    GroupWarning,
)

class GroupChallengeAPITests(APITestCase):

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

        self.today = date(2026, 11, 25)

        patcher = patch(
            "groups.challenge_services.get_local_today",
            return_value=self.today,
        )

        patcher.start()
        self.addCleanup(patcher.stop)

        self.owner = self.create_user(
            "+989121234593",
            "challenge_owner",
        )

        self.member = self.create_user(
            "+989121234594",
            "challenge_member",
        )

        self.other = self.create_user(
            "+989121234595",
            "challenge_other",
        )

        self.group = HabitGroup.objects.create(
            owner=self.owner,
            name="Study Group",
            visibility="private",
        )

        self.owner_membership = (
            GroupMembership.objects.create(
                group=self.group,
                user=self.owner,
                role="owner",
                can_manage_members=True,
                can_manage_challenges=True,
                can_warn_members=True,
            )
        )

        self.member_membership = (
            GroupMembership.objects.create(
                group=self.group,
                user=self.member,
                role="member",
            )
        )

        self.start = self.today - timedelta(days=3)

        GroupMembership.objects.filter(
            group=self.group,
        ).update(
            joined_at=datetime(
                self.start.year,
                self.start.month,
                self.start.day,
                tzinfo=dt_timezone.utc,
            )
        )

        self.challenge = GroupChallenge.objects.create(
            group=self.group,
            title="Study",
            kind="count",
            polarity="positive",
            target_value=20,
            unit="pages",
            frequency="daily",
            start_date=self.start,
            duration_days=40,
            timezone="UTC",
            failure_policy="warn",
            failure_limit=3,
        )

        self.list_url = (
            f"/api/groups/{self.group.pk}/challenges/"
        )

        self.base_url = (
            f"{self.list_url}{self.challenge.pk}/"
        )

        self.client.force_authenticate(
            user=self.owner
        )

    def test_create_challenge_permissions(self):

        payload = {
            "title": "Exercise",
            "kind": "time",
            "polarity": "positive",
            "target_value": 20,
            "unit": "minutes",
            "frequency": "daily",
            "start_date": str(self.today),
            "duration_days": 40,
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 403
        )

    def test_record_log_and_progress(self):

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.put(
            f"{self.base_url}logs/{self.today}/",
            {"value": 25},
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        self.assertTrue(response.data["success"])

        response = self.client.put(
            f"{self.base_url}logs/{self.today}/",
            {"value": 30},
            format="json",
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertEqual(
            GroupHabitLog.objects.filter(
                challenge=self.challenge,
                membership=self.member_membership,
            ).count(),
            1,
        )

        response = self.client.get(
            f"{self.base_url}progress/"
        )

        self.assertEqual(
            response.status_code, 200
        )

        member_data = next(
            item for item in response.data
            if item["user_id"] == self.member.pk
        )

        self.assertEqual(
            member_data["successful_periods"], 1
        )

        self.assertEqual(
            member_data["progress_percent"], 2.5
        )

        self.assertEqual(
            member_data["current_streak"], 1
        )

        # The owner cannot read another member's raw logs.
        self.client.force_authenticate(
            user=self.owner
        )

        response = self.client.get(
            f"{self.base_url}logs/"
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertEqual(
            response.data, []
        )

    def test_outsider_cannot_access_progress(self):

        self.client.force_authenticate(
            user=self.other
        )

        response = self.client.get(
            f"{self.base_url}progress/"
        )

        self.assertEqual(
            response.status_code, 404
        )

    def test_warning_policy(self):

        payload = {
            "user_id": self.member.pk
        }

        response = self.client.post(
            f"{self.base_url}apply-policy/",
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertEqual(
            response.data["action"], "warn"
        )

        warning_id = response.data["warning_id"]

        # Repeated calls must not duplicate the warning.
        response = self.client.post(
            f"{self.base_url}apply-policy/",
            payload,
            format="json",
        )

        self.assertEqual(
            response.data["warning_id"],
            warning_id,
        )

        self.assertEqual(
            GroupWarning.objects.count(), 1
        )

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.get(
            f"{self.base_url}warnings/"
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertEqual(
            len(response.data), 1
        )

    def test_remove_policy_revokes_access(self):

        self.challenge.failure_policy = "remove"

        self.challenge.save(
            update_fields=["failure_policy"]
        )

        response = self.client.post(
            f"{self.base_url}apply-policy/",
            {
                "user_id": self.member.pk
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertEqual(
            response.data["action"], "remove"
        )

        self.assertFalse(
            GroupMembership.objects.filter(
                group=self.group,
                user=self.member,
            ).exists()
        )

        self.client.force_authenticate(
            user=self.member
        )

        response = self.client.get(
            f"{self.base_url}progress/"
        )

        self.assertEqual(
            response.status_code, 404
        )

    def test_late_join_has_no_old_failures(self):

        GroupMembership.objects.filter(
            pk=self.member_membership.pk,
        ).update(
            joined_at=datetime(
                self.today.year,
                self.today.month,
                self.today.day,
                tzinfo=dt_timezone.utc,
            )
        )

        response = self.client.get(
            f"{self.base_url}progress/"
        )

        member_data = next(
            item for item in response.data
            if item["user_id"] == self.member.pk
        )

        self.assertEqual(
            member_data["consecutive_failures"], 0
        )

        self.assertFalse(
            member_data["policy_triggered"]
        )

    def test_policy_before_failure_limit(self):

        self.challenge.failure_limit = 4

        self.challenge.save(
            update_fields=["failure_limit"]
        )

        response = self.client.post(
            f"{self.base_url}apply-policy/",
            {
                "user_id": self.member.pk
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, 400
        )

        self.assertEqual(
            GroupWarning.objects.count(), 0
        )

    def test_admin_without_warning_permission(self):

        admin_membership = (
            GroupMembership.objects.create(
                group=self.group,
                user=self.other,
                role="admin",
                can_manage_members=True,
                can_warn_members=False,
            )
        )

        self.client.force_authenticate(
            user=self.other
        )

        response = self.client.post(
            f"{self.base_url}apply-policy/",
            {
                "user_id": self.member.pk
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, 403
        )

        admin_membership.can_warn_members = True

        admin_membership.save(
            update_fields=["can_warn_members"]
        )

        response = self.client.post(
            f"{self.base_url}apply-policy/",
            {
                "user_id": self.member.pk
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, 200
        )